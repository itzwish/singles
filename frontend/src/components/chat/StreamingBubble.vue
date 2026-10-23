<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  content: string
  avatarName?: string
  avatarUrl?: string | null
}>()

const filtered = computed(() => {
  return props.content.replace(/\[image[:：].*?\]/gis, '')
})
</script>

<template>
  <div class="message assistant">
    <div class="msg-avatar">
      <img v-if="avatarUrl" :src="avatarUrl" class="avatar-img" alt="" />
      <span v-else>{{ avatarName || '?' }}</span>
    </div>
    <div class="msg-content">
      <div class="msg-bubble">
        {{ filtered }}<span class="cursor">|</span>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  gap: 8px;
  max-width: 70%;
  align-self: flex-start;
  animation: msgIn 180ms var(--ease-smooth);
}
.msg-avatar {
  width: 36px;
  height: 36px;
  border-radius: 10px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 15px;
  font-weight: 600;
  font-family: var(--font-heading);
  margin-top: 2px;
  background: var(--color-sakura);
  overflow: hidden;
}
.avatar-img {
  width: 100%;
  height: 100%;
  border-radius: inherit;
  object-fit: cover;
}
.msg-bubble {
  padding: 12px 16px;
  border-radius: 10px;
  background: var(--color-bubble-ai);
  color: var(--color-text);
  font-size: 16px;
  line-height: 1.55;
  word-break: break-word;
  font-family: var(--font-body);
}
.cursor {
  display: inline-block;
  animation: blink 1s step-end infinite;
  color: var(--color-primary);
  font-weight: 300;
}
@keyframes blink {
  50% { opacity: 0; }
}
@keyframes msgIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .message { animation: none; }
}
</style>
