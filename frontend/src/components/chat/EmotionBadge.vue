<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/stores/chat'

const chat = useChatStore()
const { emotionState } = storeToRefs(chat)

const emotionMap: Record<string, { label: string; color: string; bg: string }> = {
  happy: { label: 'Happy', color: '#D4A853', bg: 'rgba(255, 212, 168, 0.15)' },
  sad: { label: 'Sad', color: '#7B9EC7', bg: 'rgba(123, 158, 199, 0.12)' },
  angry: { label: 'Angry', color: '#E8808A', bg: 'rgba(232, 128, 138, 0.12)' },
  anxious: { label: 'Anxious', color: '#C4A1FF', bg: 'rgba(196, 161, 255, 0.12)' },
  calm: { label: 'Calm', color: '#8CBD8C', bg: 'rgba(140, 189, 140, 0.12)' },
  excited: { label: 'Excited', color: '#FF7DAF', bg: 'rgba(255, 125, 175, 0.12)' },
  other: { label: 'Other', color: '#C495A8', bg: 'rgba(196, 149, 168, 0.1)' },
}

const emotion = computed(() => {
  if (!emotionState.value) return null
  const primary = emotionState.value.primary || 'calm'
  return emotionMap[primary] || emotionMap['other']
})

const intensityPct = computed(() => {
  if (!emotionState.value) return 0
  return ((emotionState.value.intensity || 5) / 10) * 100
})
</script>

<template>
  <Transition name="fade">
    <div
      v-if="emotion"
      class="emotion-badge"
      :style="{ '--emo-color': emotion.color, '--emo-bg': emotion.bg }"
    >
      <span class="emo-dot" />
      <span class="emo-label">{{ emotion.label }}</span>
      <div class="emo-bar-track">
        <div class="emo-bar-fill" :style="{ width: intensityPct + '%' }" />
      </div>
    </div>
  </Transition>
</template>

<style scoped>
.emotion-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  background: var(--emo-bg);
  border: 1px solid color-mix(in srgb, var(--emo-color) 20%, transparent);
  border-radius: var(--radius-full);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  transition: all var(--duration) var(--ease-smooth);
}

.emo-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--emo-color);
}

.emo-label {
  color: var(--color-text-secondary);
  font-weight: 500;
}

.emo-bar-track {
  width: 44px;
  height: 3px;
  background: color-mix(in srgb, var(--emo-color) 10%, transparent);
  border-radius: var(--radius-full);
  overflow: hidden;
}

.emo-bar-fill {
  height: 100%;
  background: var(--emo-color);
  border-radius: var(--radius-full);
  transition: width var(--duration) var(--ease-smooth);
}

.fade-enter-active, .fade-leave-active {
  transition: opacity var(--duration-fast), transform var(--duration-fast) var(--ease-smooth);
}
.fade-enter-from, .fade-leave-to {
  opacity: 0;
  transform: scale(0.9);
}
</style>
