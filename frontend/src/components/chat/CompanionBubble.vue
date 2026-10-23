<script setup lang="ts">
/**
 * CompanionBubble — plays back a full companion response with:
 *   1. read_delay_ms  → shows the user message as "Seen" after the delay
 *   2. Per-bubble:
 *      a. ghost_typing_ms (optional) → show typing indicator, then hide it
 *      b. pause_before_ms            → silent pause
 *      c. typing_ms                  → show typing indicator
 *      d. append bubble text to the chat
 *
 * Usage: mount it after receiving the companion payload; it auto-plays on mount.
 * Emits 'done' when all bubbles have been delivered.
 * Emits 'seenAt' as soon as read_delay_ms elapses.
 */
import { ref, onMounted, onUnmounted } from 'vue'
import TypingIndicator from '@/components/chat/TypingIndicator.vue'

export interface Bubble {
  text: string
  pause_before_ms: number
  ghost_typing_ms: number
  typing_ms: number
}

const props = defineProps<{
  bubbles: Bubble[]
  readDelayMs: number
  avatarName?: string
  avatarUrl?: string | null
}>()

const emit = defineEmits<{
  (e: 'bubbleReady', text: string): void
  (e: 'seenAt'): void
  (e: 'done'): void
  (e: 'typingStart'): void
  (e: 'typingStop'): void
}>()

const showTyping = ref(false)
let cancelled = false

function sleep(ms: number): Promise<void> {
  return new Promise(resolve => {
    const id = setTimeout(resolve, Math.max(0, ms))
    // store handle so we can cancel on unmount if needed
    handles.push(id)
  })
}

const handles: ReturnType<typeof setTimeout>[] = []

async function play() {
  // 1. read delay
  await sleep(props.readDelayMs)
  if (cancelled) return
  emit('seenAt')

  // 2. iterate bubbles
  for (const bubble of props.bubbles) {
    if (cancelled) return

    // 2a. ghost typing (user typed then deleted)
    if (bubble.ghost_typing_ms > 0) {
      showTyping.value = true
      emit('typingStart')
      await sleep(bubble.ghost_typing_ms)
      if (cancelled) return
      showTyping.value = false
      emit('typingStop')
    }

    // 2b. pause before this bubble
    await sleep(bubble.pause_before_ms)
    if (cancelled) return

    // 2c. real typing indicator
    showTyping.value = true
    emit('typingStart')
    await sleep(bubble.typing_ms)
    if (cancelled) return
    showTyping.value = false
    emit('typingStop')

    // 2d. deliver bubble
    emit('bubbleReady', bubble.text)
  }

  emit('done')
}

onMounted(() => { play() })

onUnmounted(() => {
  cancelled = true
  handles.forEach(h => clearTimeout(h))
})
</script>

<template>
  <div class="companion-playback">
    <!-- Live typing indicator -->
    <div v-if="showTyping" class="typing-wrapper">
      <div class="msg-avatar small">
        <img v-if="avatarUrl" :src="avatarUrl" class="avatar-img" alt="" />
        <span v-else>{{ avatarName || '?' }}</span>
      </div>
      <TypingIndicator />
    </div>
  </div>
</template>

<style scoped>
.companion-playback {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.msg-avatar.small {
  width: 28px;
  height: 28px;
  font-size: 13px;
}

.avatar-img {
  width: 100%;
  height: 100%;
  border-radius: inherit;
  object-fit: cover;
}

.typing-wrapper {
  display: flex;
  align-items: center;
  gap: 10px;
  align-self: flex-start;
}
</style>
