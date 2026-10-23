<script setup lang="ts">
import { computed, onMounted, onUnmounted, watch, ref, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import { useAutoScroll } from '@/composables/useAutoScroll'
import TopBar from '@/components/layout/TopBar.vue'
import MessageBubble from '@/components/chat/MessageBubble.vue'
import StreamingBubble from '@/components/chat/StreamingBubble.vue'
import CompanionBubble from '@/components/chat/CompanionBubble.vue'
import TypingIndicator from '@/components/chat/TypingIndicator.vue'
import ChatInput from '@/components/input/ChatInput.vue'
import EmotionBadge from '@/components/chat/EmotionBadge.vue'
import { Bot, MessageCircle, Trash2 } from 'lucide-vue-next'
import api from '@/utils/http'

const props = defineProps<{ characterId: string }>()

const router = useRouter()
const chat = useChatStore()
const auth = useAuthStore()
const { currentCharacter, messages, isStreaming, streamingContent,
        companionMode, companionPayload, companionPlaying } = storeToRefs(chat)
const { userAvatar } = storeToRefs(auth)

// "Seen" receipt: shown below the last user bubble after read_delay_ms fires
const seenVisible = ref(false)

const displayMessages = computed(() =>
  messages.value.filter((m): m is typeof m & { role: 'user' | 'assistant' } =>
    m.role === 'user' || m.role === 'assistant'
  )
)

const messageContainer = ref<HTMLElement | null>(null)
const { onNewContent, scrollToBottom, checkScrollPosition } = useAutoScroll(messageContainer)

const loading = ref(true)
const loadError = ref('')

onMounted(async () => {
  try {
    await chat.selectCharacter(props.characterId)
    await auth.loadUserInfo()
    // Auto-enable companion mode if the character was configured as a companion
    const profile = chat.currentCharacter?.personality_profile || {}
    if (profile.companion_gender_role) {
      chat.companionMode = true
    }
  } catch (e: any) {
    loadError.value = e?.response?.data?.detail || 'Could not load this character'
  } finally {
    loading.value = false
    await nextTick()
    scrollToBottom(false)
  }
})

onUnmounted(() => {
  chat.disconnectWebSocket()
})

watch(
  () => [messages.value.length, streamingContent.value],
  () => onNewContent(),
)

function onSend(text: string, image: string | null) {
  seenVisible.value = false
  if (companionMode.value) {
    chat.sendCompanionMessage(text, image)
  } else {
    chat.sendMessage(text, image)
  }
}

function goBack() {
  router.push({ name: 'home' })
}

function formatTime(iso: string) {
  return new Date(iso).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' })
}

function formatDate() {
  const d = new Date()
  return d.toLocaleDateString('en-US', { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' })
}

function onRecall(msgId: string) {
  chat.recallMessage(msgId)
}
function onRetry(msgId: string) {
  chat.retryMessage(msgId)
}

const deletingConv = ref(false)
async function deleteCurrentConv() {
  if (!chat.currentConversation) return
  if (!confirm('Delete this conversation and all its messages? This cannot be undone.')) return
  deletingConv.value = true
  try {
    await api.delete(`/conversations/${chat.currentConversation.id}`)
    chat.currentConversation = null
    chat.messages = []
    router.push({ name: 'home' })
  } catch (e: any) {
    alert(e?.response?.data?.detail || 'Delete failed')
  } finally {
    deletingConv.value = false
  }
}
</script>

<template>
  <div class="chat-view">
    <TopBar
      :title="currentCharacter?.name"
      :show-back="true"
      @back="goBack"
    >
      <template #actions>
        <!-- Companion mode toggle -->
        <button
          type="button"
          :class="['action-btn', 'companion-toggle', { active: companionMode }]"
          :title="companionMode ? 'Companion mode on' : 'Companion mode off'"
          :aria-pressed="companionMode"
          @click="chat.companionMode = !chat.companionMode"
        >
          <MessageCircle v-if="companionMode" :size="18" />
          <Bot v-else :size="18" />
        </button>
        <button
          type="button"
          class="action-btn danger"
          :disabled="deletingConv || !chat.currentConversation"
          title="Delete conversation"
          @click="deleteCurrentConv"
        >
          <Trash2 :size="18" />
        </button>
      </template>
    </TopBar>

    <!-- Loading -->
    <div v-if="loading" class="chat-status">
      <div class="status-spinner" />
      <span>Loading...</span>
    </div>

    <!-- Error -->
    <div v-else-if="loadError" class="chat-status">
      <span class="status-error">{{ loadError }}</span>
      <button class="status-btn" @click="goBack">Back home</button>
    </div>

    <!-- Chat -->
    <template v-else>
      <main
        class="chat-messages"
        ref="messageContainer"
        @scroll="checkScrollPosition"
      >
        <div class="date-divider">{{ formatDate() }}</div>

        <MessageBubble
          v-for="(m, i) in displayMessages"
          :key="m.id"
          :role="m.role"
          :content="m.content"
          :time="formatTime(m.created_at)"
          :content-type="m.content_type"
          :metadata="m.metadata"
          :message-id="m.id"
          :is-last="i === displayMessages.length - 1"
          :avatar-name="m.role === 'assistant' ? currentCharacter?.name?.[0] : undefined"
          :avatar-url="m.role === 'assistant' ? chat.getAvatarUrl(currentCharacter?.avatar_url, currentCharacter?.id) : undefined"
          :user-avatar-url="m.role === 'user' ? userAvatar : undefined"
          @recall="onRecall"
          @retry="onRetry"
        />

        <!-- Companion mode playback (replaces StreamingBubble / TypingIndicator) -->
        <CompanionBubble
          v-if="companionMode && companionPayload"
          :bubbles="companionPayload.bubbles"
          :read-delay-ms="companionPayload.read_delay_ms"
          :avatar-name="currentCharacter?.name?.[0]"
          :avatar-url="chat.getAvatarUrl(currentCharacter?.avatar_url, currentCharacter?.id)"
          @bubble-ready="chat.onCompanionBubbleReady"
          @seen-at="seenVisible = true"
          @done="chat.onCompanionPlaybackDone"
        />

        <!-- Companion loading indicator (payload not yet returned) -->
        <TypingIndicator v-else-if="companionMode && companionPlaying && !companionPayload" />

        <!-- Legacy streaming (non-companion mode) -->
        <StreamingBubble
          v-else-if="!companionMode && isStreaming && streamingContent"
          :content="streamingContent"
          :avatar-name="currentCharacter?.name?.[0]"
          :avatar-url="chat.getAvatarUrl(currentCharacter?.avatar_url, currentCharacter?.id)"
        />

        <TypingIndicator v-else-if="!companionMode && isStreaming && !streamingContent" />

        <!-- "Seen" receipt below last user message -->
        <div v-if="seenVisible && companionMode" class="seen-receipt">Seen</div>
      </main>

      <div class="input-area">
        <EmotionBadge />
        <ChatInput @send="onSend" />
      </div>
    </template>

    <!-- API key warning dialog -->

  </div>
</template>

<style scoped>
.chat-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

/* The scroller stays full width; the conversation is centred in a readable column. */
.chat-messages {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 20px max(24px, calc((100% - 880px) / 2));
}
/* A short conversation sits at the bottom, where the next message goes. */
.chat-messages > :first-child {
  margin-top: auto;
}

.date-divider {
  text-align: center;
  font-size: var(--text-xs);
  font-family: var(--font-body);
  color: var(--color-text-secondary);
  padding: 8px 0;
  margin-bottom: 4px;
}

/* ── Status (loading / error) ── */
.chat-status {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 16px;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.status-spinner {
  width: 32px;
  height: 32px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.status-error {
  color: var(--color-error-ink);
}

.status-btn {
  padding: 9px 20px;
  background: var(--color-action);
  color: #fff;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-weight: 600;
  font-family: var(--font-body);
  cursor: pointer;
  transition: background-color 140ms var(--ease-smooth);
}
.status-btn:hover {
  background: var(--color-action-hover);
}

.action-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: none;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: background-color 140ms var(--ease-smooth), color 140ms var(--ease-smooth);
}
.action-btn:hover {
  background: var(--color-sakura);
  color: var(--color-text);
}
.action-btn.danger:hover {
  background: var(--color-error);
  color: #fff;
}
.action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.action-btn:focus-visible {
  outline: 2px solid var(--color-action);
  outline-offset: 2px;
}

.companion-toggle.active {
  background: var(--color-sakura);
  color: var(--color-action);
}

.input-area {
  display: flex;
  flex-direction: column;
  align-items: center;
  width: 100%;
  max-width: 880px;
  margin: 0 auto;
  padding: 0 0 8px;
}
.input-area :deep(.chat-input-area) {
  width: 100%;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* Companion "Seen" read receipt */
.seen-receipt {
  align-self: flex-end;
  font-size: 12px;
  color: var(--color-text-secondary);
  margin-top: -8px;
  padding-right: 4px;
  animation: fadeIn 0.3s ease;
}
@keyframes fadeIn {
  from { opacity: 0; }
  to   { opacity: 0.75; }
}

@media (max-width: 768px) {
  .chat-messages {
    padding: 12px 16px;
    gap: 10px;
  }
  .input-area {
    padding: 0 12px 6px;
    padding-bottom: max(6px, env(safe-area-inset-bottom));
  }
}

@media (max-width: 480px) {
  .chat-messages {
    padding: 10px 12px;
    gap: 8px;
  }
  .input-area {
    padding: 0 8px 4px;
    padding-bottom: max(4px, env(safe-area-inset-bottom));
  }
}

/* ── API Key Warning Dialog ── */
.api-key-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.45);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease;
}
.api-key-dialog {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  padding: 28px 24px 22px;
  max-width: 380px;
  width: 90%;
  text-align: left;
  animation: scaleIn 0.2s var(--ease-smooth);
}
.api-key-dialog h3 {
  font-size: 20px;
  font-weight: 600;
  font-family: var(--font-heading);
  color: var(--color-text);
  margin: 0 0 8px;
}
.api-key-dialog p {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin: 0 0 20px;
  line-height: 1.6;
}
.dialog-actions {
  display: flex;
  gap: 10px;
  justify-content: flex-end;
}
.dialog-btn {
  padding: 8px 20px;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast);
  border: none;
}
.dialog-btn.cancel {
  background: var(--color-surface);
  color: var(--color-text-secondary);
}
.dialog-btn.cancel:hover { background: var(--color-border); }
.dialog-btn.confirm {
  background: var(--color-action);
  color: #fff;
}
.dialog-btn.confirm:hover { background: var(--color-action-hover); }

@keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes scaleIn { from { opacity: 0; transform: scale(0.97); } to { opacity: 1; transform: scale(1); } }
</style>
