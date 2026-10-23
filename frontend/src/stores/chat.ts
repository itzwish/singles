import { defineStore } from 'pinia'
import { ref } from 'vue'
import api, { uploadApi, resolveAuthToken } from '@/utils/http'
import { useAuthStore } from '@/stores/auth'
import type { Character, Conversation, Message, Memory } from '@/types/models'

// ── Companion mode types ──
export interface CompanionBubble {
  text: string
  pause_before_ms: number
  ghost_typing_ms: number
  typing_ms: number
}

export interface CompanionPayload {
  internal_state: {
    current_mood: string
    valence: number
    energy: number
    busyness_level: number
    effective_wpm: number
    current_activity: string
    unfiltered_thought: string
  }
  read_delay_ms: number
  bubbles: CompanionBubble[]
  next_spontaneous_trigger_minutes: number
}

// crypto.randomUUID is unavailable over plain HTTP, so fall back manually
function genUUID(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID()
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, c => {
    const r = Math.random() * 16 | 0
    return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16)
  })
}

export const useChatStore = defineStore('chat', () => {
  const characters = ref<Character[]>([])
  const currentCharacter = ref<Character | null>(null)
  const conversations = ref<Conversation[]>([])
  const currentConversation = ref<Conversation | null>(null)
  const messages = ref<Message[]>([])
  const isStreaming = ref(false)
  const streamingContent = ref('')
  const streamingComplete = ref(false) // used for the transition animation
  const ws = ref<WebSocket | null>(null)
  const wsReconnectAttempts = ref(0)
  const wsIntentionalClose = ref(false)
  // Flips to true once WebSocket upgrades have proven unavailable on this
  // deployment, so later sends skip the connect-and-retry delay entirely.
  const wsUnavailable = ref(false)
  let _wsReconnectTimer: ReturnType<typeof setTimeout> | null = null
  function _clearWsReconnectTimer() {
    if (_wsReconnectTimer !== null) {
      clearTimeout(_wsReconnectTimer)
      _wsReconnectTimer = null
    }
  }
  const emotionState = ref<{ primary: string; intensity: number; valence: number } | null>(null)

  // Memories
  const memories = ref<Memory[]>([])

  // ── Companion mode ──
  // Set to true to route sendMessage() through the companion pipeline instead
  // of the legacy WebSocket/SSE pipeline.
  const companionMode = ref(false)
  // Holds the latest structured payload returned by /companion/chat or /companion/tick
  const companionPayload = ref<CompanionPayload | null>(null)
  // Whether the companion playback queue is currently animating
  const companionPlaying = ref(false)
  // Idle-tick timer handle
  let _tickTimer: ReturnType<typeof setTimeout> | null = null

  function _clearTickTimer() {
    if (_tickTimer !== null) {
      clearTimeout(_tickTimer)
      _tickTimer = null
    }
  }

  function _scheduleIdleTick(minutes: number, conversationId: string) {
    _clearTickTimer()
    if (minutes <= 0) return
    _tickTimer = setTimeout(async () => {
      // Only fire if the user still hasn't sent anything in the meantime
      try {
        const res = await api.post<CompanionPayload>('/companion/tick', {
          conversation_id: conversationId,
        })
        if (res.data.bubbles && res.data.bubbles.length > 0) {
          companionPayload.value = res.data
        }
        // Reschedule with the new trigger time
        _scheduleIdleTick(res.data.next_spontaneous_trigger_minutes, conversationId)
      } catch {
        // silent — tick failures are non-fatal
      }
    }, minutes * 60 * 1000)
  }

  async function sendCompanionMessage(text: string, image?: string | null) {
    const auth = useAuthStore()
    if (!auth.hasApiKey) {
      auth.promptApiKey()
      return
    }
    if (!currentConversation.value) return

    // Cancel any pending idle tick since the user just sent a message
    _clearTickTimer()

    // Push the user's bubble into the UI immediately
    messages.value.push({
      id: genUUID(),
      role: 'user',
      content: text || '[Photo]',
      content_type: image ? 'image' : 'text',
      metadata: image ? { image_base64: image } : null,
      emotion_label: null,
      created_at: new Date().toISOString(),
    })

    companionPlaying.value = true
    companionPayload.value = null

    try {
      const res = await api.post<CompanionPayload>('/companion/chat', {
        conversation_id: currentConversation.value.id,
        message: text,
      })
      companionPayload.value = res.data
      // Schedule the next idle tick
      _scheduleIdleTick(
        res.data.next_spontaneous_trigger_minutes,
        currentConversation.value.id,
      )
    } catch (e: any) {
      companionPlaying.value = false
      messages.value.push({
        id: genUUID(),
        role: 'assistant',
        content: e?.response?.data?.detail || 'Something went wrong. Try again in a bit.',
        content_type: 'text',
        metadata: null,
        emotion_label: null,
        created_at: new Date().toISOString(),
      })
    }
  }

  // Called by CompanionBubble.vue after each bubble is delivered
  function onCompanionBubbleReady(text: string) {
    messages.value.push({
      id: genUUID(),
      role: 'assistant',
      content: text,
      content_type: 'text',
      metadata: null,
      emotion_label: null,
      created_at: new Date().toISOString(),
    })
  }

  // Called by CompanionBubble.vue when all bubbles have been delivered
  function onCompanionPlaybackDone() {
    companionPlaying.value = false
    companionPayload.value = null
  }

  async function loadCharacters() {
    const res = await api.get<Character[]>('/characters')
    characters.value = res.data
  }

  async function selectCharacter(characterId: string) {
    let char = characters.value.find(c => c.id === characterId)
    if (!char) {
      // Not in the store yet (e.g. after a hard refresh) — load it from the API
      try {
        const res = await api.get<Character>(`/characters/${characterId}`)
        char = res.data
        if (!characters.value.find(c => c.id === char!.id)) {
          characters.value.push(char)
        }
      } catch {
        throw new Error('Character not found')
      }
    }
    if (!char) throw new Error('Character not found')
    currentCharacter.value = char
    // Reset streaming state so a half-finished reply can't leave the bar stuck
    isStreaming.value = false
    streamingContent.value = ''
    streamingComplete.value = false
    emotionState.value = null

    // Load every conversation with this character as short-term memory
    const convRes = await api.get<Conversation[]>('/conversations', {
      params: { character_id: char.id },
    })
    if (convRes.data.length > 0) {
      conversations.value = convRes.data
      currentConversation.value = convRes.data[0]
    } else {
      const res = await api.post('/conversations', null, {
        params: { character_id: char.id },
      })
      conversations.value = [res.data]
      currentConversation.value = res.data
    }
    messages.value = []
    wsIntentionalClose.value = true
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    wsIntentionalClose.value = false
    await loadMessages()
    await loadMemories(characterId)
    connectWebSocket()

    // Interruption check: the last message is from the user with no AI reply → resend it
    const msgs = messages.value
    if (msgs.length > 0 && msgs[msgs.length - 1].role === 'user') {
      const last = msgs.pop()!
      // Give the WebSocket a moment to connect
      setTimeout(() => {
        sendMessage(last.content, last.metadata?.image_base64)
      }, 600)
    }
  }

  async function createCharacter(data: {
    name: string
    description: string
    system_prompt?: string
    personality_profile?: Record<string, any> | null
  }) {
    const res = await api.post<Character>('/characters', data)
    characters.value.push(res.data)
    return res.data
  }

  async function generateCharacterProfile(description: string): Promise<Record<string, any>> {
    const res = await api.post<{ personality_profile: Record<string, any> }>(
      '/characters/generate',
      { user_description: description },
      { timeout: 120000 },
    )
    return res.data.personality_profile
  }

  async function analyzeChatLogs(chatText: string, currentProfile?: Record<string, any> | null) {
    const res = await api.post<{
      enhanced_profile: Record<string, any>
    }>('/characters/analyze-chat', {
      chat_text: chatText,
      current_profile: currentProfile || null,
    }, { timeout: 120000 })
    return res.data
  }

  async function uploadCharacterDocuments(characterId: string, files: File[]) {
    for (const file of files) {
      const form = new FormData()
      form.append('file', file)
      await uploadApi.post(`/characters/${characterId}/documents`, form)
    }
  }

  async function updateCharacter(id: string, data: { name?: string; description?: string; system_prompt?: string; personality_profile?: Record<string, any> | null }) {
    const res = await api.patch<Character>(`/characters/${id}`, data)
    const idx = characters.value.findIndex(c => c.id === id)
    if (idx >= 0) characters.value[idx] = res.data
    if (currentCharacter.value?.id === id) currentCharacter.value = res.data
    return res.data
  }

  async function deleteCharacter(id: string) {
    await api.delete(`/characters/${id}`)
    characters.value = characters.value.filter(c => c.id !== id)
  }

  async function uploadAvatar(characterId: string, file: File) {
    const form = new FormData()
    form.append('file', file)
    const res = await uploadApi.post<Character>(`/characters/${characterId}/avatar`, form)
    // Refresh the avatar in both the list and the active character
    const idx = characters.value.findIndex(c => c.id === characterId)
    if (idx >= 0) characters.value[idx] = res.data
    if (currentCharacter.value?.id === characterId) currentCharacter.value = res.data
    characterAvatarVersion.value[characterId] = (characterAvatarVersion.value[characterId] || 0) + 1
    return res.data
  }

  async function loadMessages() {
    if (conversations.value.length === 0) return
    const results = await Promise.all(
      conversations.value.map(conv =>
        api.get<Message[]>(`/conversations/${conv.id}/messages`)
      )
    )
    const allMessages = results.flatMap(r => r.data)
    allMessages.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
    messages.value = allMessages
  }

  // ── Memories ──

  async function loadMemories(characterId?: string) {
    const cid = characterId || currentCharacter.value?.id
    if (!cid) return
    try {
      const res = await api.get<Memory[]>('/memories', { params: { character_id: cid } })
      memories.value = res.data
    } catch { /* ignore */ }
  }

  async function updateMemory(id: string, data: { content?: string; importance?: number }) {
    await api.patch(`/memories/${id}`, data)
    const idx = memories.value.findIndex(m => m.id === id)
    if (idx >= 0) {
      if (data.content !== undefined) memories.value[idx].content = data.content
      if (data.importance !== undefined) memories.value[idx].importance = data.importance
    }
  }

  async function deleteMemory(id: string) {
    await api.delete(`/memories/${id}`)
    memories.value = memories.value.filter(m => m.id !== id)
  }

  const characterAvatarVersion = ref<Record<string, number>>({})

  function getAvatarUrl(avatarUrl: string | null | undefined, characterId?: string): string {
    if (!avatarUrl) return ''
    const v = characterId ? (characterAvatarVersion.value[characterId] || 0) : 0
    return v > 0 ? `${avatarUrl}?v=${v}` : avatarUrl
  }

  const consolidating = ref(false)
  async function consolidateMemories(characterId?: string | null) {
    const cid = characterId || currentCharacter.value?.id
    if (!cid) return
    consolidating.value = true
    try {
      const res = await api.post('/memories/consolidate', null, { params: { character_id: cid } })
      if (res.data.consolidated) {
        await loadMemories(cid)
      }
      return res.data
    } finally {
      consolidating.value = false
    }
  }

  // ── Streaming transport ──
  //
  // WebSocket is the primary transport. Deployments without WebSocket support
  // (notably Vercel serverless) transparently fall back to SSE, which carries
  // exactly the same event shapes through `handleServerEvent`.

  /** Apply one server event. Shared by the WebSocket and SSE transports. */
  function handleServerEvent(data: any) {
    if (data.type === 'chunk') {
      if (!isStreaming.value) isStreaming.value = true
      streamingContent.value += data.content
    } else if (data.type === 'done') {
      streamingComplete.value = true
      if (data.full_reply && data.full_reply.trim()) {
        messages.value.push({
          id: genUUID(),
          role: 'assistant',
          content: data.full_reply,
          content_type: 'text',
          metadata: null,
          emotion_label: null,
          created_at: new Date().toISOString(),
        })
      }
      if (data.emotion_state) {
        emotionState.value = data.emotion_state
      }
      // Clear the streaming content once the transition animation is done
      setTimeout(() => {
        streamingContent.value = ''
        streamingComplete.value = false
      }, 300)
      isStreaming.value = false
    } else if (data.type === 'ai_error') {
      isStreaming.value = false
      streamingContent.value = ''
      streamingComplete.value = false
      const errorMessages: Record<string, string> = {
        invalid_key: 'That API key is not valid. Add a new one in your profile.',
        invalid_model: 'That model is not available. Pick another model in your profile.',
        server_error: 'The AI service is having a moment. Try again in a bit.',
        empty_reply: 'I lost my train of thought there... could you say that again?',
        unknown: "The AI call didn't go through. Try again in a bit.",
      }
      // Rate-limit errors carry a specific wait time from the backend, so the
      // server message wins over a generic wording.
      const msg = errorMessages[data.code] || data.message || 'The AI call failed'
      messages.value.push({
        id: genUUID(),
        role: 'assistant',
        content: msg,
        content_type: 'text',
        metadata: { error_code: data.code },
        emotion_label: null,
        created_at: new Date().toISOString(),
      })
    } else if (data.type === 'error') {
      isStreaming.value = false
      streamingContent.value = ''
      streamingComplete.value = false
      messages.value.push({
        id: genUUID(),
        role: 'assistant',
        content: 'Oops… something went wrong just now (′；ω；`) Could you say that again?',
        content_type: 'text',
        metadata: null,
        emotion_label: null,
        created_at: new Date().toISOString(),
      })
      console.error(data.message)
    }
  }

  async function connectWebSocket() {
    // If a reconnect is already scheduled, let it handle the retry instead of
    // starting another competing connection.
    if (_wsReconnectTimer !== null) return

    if (ws.value) {
      wsIntentionalClose.value = true
      ws.value.close()
      ws.value = null
      wsIntentionalClose.value = false
    }

    if (!currentConversation.value || wsUnavailable.value) return

    // A WebSocket frame cannot carry a bearer header, so the backend hands
    // out a short-lived ticket for the handshake.
    let token = ''
    try {
      const res = await api.post<{ ticket: string; expires_in: number }>('/auth/ws-ticket')
      token = res.data.ticket
    } catch {
      token = (await resolveAuthToken()) || 'guest'
    }

    // The socket may have been closed while the ticket was being fetched
    if (wsIntentionalClose.value || !currentConversation.value) return

    const convId = currentConversation.value.id
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/chat/${convId}`)
    ws.value = socket

    socket.onopen = () => {
      wsReconnectAttempts.value = 0
      socket.send(JSON.stringify({ type: 'auth', token }))
    }

    socket.onmessage = (event) => {
      handleServerEvent(JSON.parse(event.data))
    }

    socket.onclose = () => {
      _clearWsReconnectTimer()
      // Do not clear ws.value here: a reconnect may be scheduled. Clearing it
      // immediately caused sendMessage() to fall back to SSE or reconnect while
      // a reconnect was already in flight, and made unexpected disconnects
      // (tab switch, network blip, server restart) require a character swap to
      // recover.
      if (!wsIntentionalClose.value && wsReconnectAttempts.value < 5) {
        const delay = Math.min(1000 * Math.pow(2, wsReconnectAttempts.value) + Math.random() * 200, 10000)
        wsReconnectAttempts.value++
        _wsReconnectTimer = setTimeout(() => {
          _wsReconnectTimer = null
          connectWebSocket()
        }, delay)
      } else if (!wsIntentionalClose.value) {
        // Retries exhausted — this deployment does not do WebSocket upgrades
        ws.value = null
        wsUnavailable.value = true
        console.warn('WebSocket unavailable, chat will stream over SSE')
      }
    }

    socket.onerror = () => {
      // Do not clear ws.value on error alone; onclose will handle reconnect.
      // Clearing it here triggered reconnect storms and premature SSE fallback.
      isStreaming.value = false
      streamingContent.value = ''
      streamingComplete.value = false
    }
  }

  /** Send a message over SSE. Used when no WebSocket is available. */
  async function sendMessageViaSSE(text: string, image?: string | null) {
    if (!currentConversation.value) {
      isStreaming.value = false
      console.error('No active conversation')
      return
    }

    const token = (await resolveAuthToken()) || ''

    try {
      const response = await fetch('/api/v1/chat/stream', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({
          conversation_id: currentConversation.value.id,
          message: text,
          image: image || null,
        }),
      })

      if (!response.ok || !response.body) {
        throw new Error(`SSE request failed with status ${response.status}`)
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        // SSE frames are separated by a blank line
        let split = buffer.indexOf('\n\n')
        while (split !== -1) {
          const frame = buffer.slice(0, split)
          buffer = buffer.slice(split + 2)
          for (const line of frame.split('\n')) {
            if (line.startsWith('data: ')) {
              try {
                handleServerEvent(JSON.parse(line.slice(6)))
              } catch {
                /* ignore malformed frame */
              }
            }
          }
          split = buffer.indexOf('\n\n')
        }
      }
    } catch (e: any) {
      isStreaming.value = false
      streamingContent.value = ''
      streamingComplete.value = false
      messages.value.push({
        id: genUUID(),
        role: 'assistant',
        content: 'I could not reach the server. Check your connection and try again.',
        content_type: 'text',
        metadata: null,
        emotion_label: null,
        created_at: new Date().toISOString(),
      })
      console.error('SSE chat failed', e)
    }
  }

  function disconnectWebSocket() {
    wsIntentionalClose.value = true
    _clearWsReconnectTimer()
    if (ws.value) {
      ws.value.close()
      ws.value = null
    }
    isStreaming.value = false
    streamingContent.value = ''
    streamingComplete.value = false
  }

  function sendMessage(text: string, image?: string | null) {
    const auth = useAuthStore()
    if (!auth.hasApiKey) {
      auth.promptApiKey()
      return
    }
    // Show the user's message in the UI right away
    messages.value.push({
      id: genUUID(),
      role: 'user',
      content: text || '[Photo]',
      content_type: image ? 'image' : 'text',
      metadata: image ? { image_base64: image } : null,
      emotion_label: null,
      created_at: new Date().toISOString(),
    })
    isStreaming.value = true
    streamingContent.value = ''
    streamingComplete.value = false

    // Prefer the WebSocket; fall back to SSE where WS upgrades are unavailable.
    if (wsUnavailable.value || !ws.value || ws.value.readyState !== WebSocket.OPEN) {
      if (!currentConversation.value) {
        isStreaming.value = false
        console.error('No active conversation')
        return
      }
      if (wsUnavailable.value) {
        void sendMessageViaSSE(text, image)
        return
      }
      connectWebSocket()
      // Wait for the connection to open, then send. If the socket closed while
      // we were waiting, onclose will have scheduled a reconnect, so keep
      // polling until either the socket is open or we give up and fall back.
      const checkAndSend = () => {
        if (!currentConversation.value) {
          isStreaming.value = false
          console.error('No active conversation')
          return
        }
        if (ws.value?.readyState === WebSocket.OPEN) {
          ws.value.send(JSON.stringify({ type: 'chat', message: text, image }))
        } else if (wsReconnectAttempts.value < 5 && !wsUnavailable.value) {
          setTimeout(checkAndSend, 300)
        } else {
          // No WebSocket on this deployment — stream over SSE instead
          ws.value = null
          wsUnavailable.value = true
          console.warn('WebSocket unavailable, falling back to SSE')
          void sendMessageViaSSE(text, image)
        }
      }
      setTimeout(checkAndSend, 500)
      return
    }
    ws.value.send(JSON.stringify({ type: 'chat', message: text, image }))
  }

  function _send(text: string, image?: string | null) {
    messages.value.push({
      id: genUUID(),
      role: 'user',
      content: text || '[Photo]',
      content_type: image ? 'image' : 'text',
      metadata: image ? { image_base64: image } : null,
      emotion_label: null,
      created_at: new Date().toISOString(),
    })
    isStreaming.value = true
    streamingContent.value = ''
    streamingComplete.value = false
    if (ws.value?.readyState === WebSocket.OPEN) {
      ws.value.send(JSON.stringify({ type: 'chat', message: text, image }))
    }
  }

  async function recallMessage(msgId: string) {
    const idx = messages.value.findIndex(m => m.id === msgId)
    if (idx < 0) return
    const msg = messages.value[idx]
    // Recalling a user message also removes the AI reply right after it
    if (msg.role === 'user') {
      const next = messages.value[idx + 1]
      if (next && next.role === 'assistant') {
        messages.value.splice(idx, 2)
        if (next.id) {
          try { await api.delete(`/conversations/${currentConversation.value!.id}/messages/${next.id}`) } catch {}
        }
      } else {
        messages.value.splice(idx, 1)
      }
    } else {
      messages.value.splice(idx, 1)
    }
    if (msg.id) {
      try { await api.delete(`/conversations/${currentConversation.value!.id}/messages/${msg.id}`) } catch {}
    }
  }

  function retryMessage(aiMsgId: string) {
    const idx = messages.value.findIndex(m => m.id === aiMsgId)
    if (idx < 1) return
    // Find the user message that came before this AI reply
    const prev = messages.value[idx - 1]
    if (prev.role !== 'user') return
    const text = prev.content
    const image = prev.metadata?.image_base64 || null
    const prevId = prev.id
    // Delete the original user message and AI reply from the DB
    if (prevId) {
      try { api.delete(`/conversations/${currentConversation.value!.id}/messages/${prevId}`) } catch {}
    }
    if (aiMsgId) {
      try { api.delete(`/conversations/${currentConversation.value!.id}/messages/${aiMsgId}`) } catch {}
    }
    // Drop the original user message and AI reply locally
    messages.value.splice(idx - 1, 2)
    // Resend the user message
    sendMessage(text, image)
  }

  return {
    characters, currentCharacter, conversations, currentConversation,
    messages, isStreaming, streamingContent, streamingComplete, emotionState,
    memories,
    loadCharacters, selectCharacter, createCharacter, generateCharacterProfile,
    analyzeChatLogs, uploadCharacterDocuments,
    loadMessages, sendMessage, connectWebSocket, disconnectWebSocket, uploadAvatar,
    updateCharacter, deleteCharacter, loadMemories, updateMemory, deleteMemory,
    consolidating, consolidateMemories,
    getAvatarUrl,
    recallMessage, retryMessage,
    // companion mode
    companionMode, companionPayload, companionPlaying,
    sendCompanionMessage, onCompanionBubbleReady, onCompanionPlaybackDone,
  }
})
