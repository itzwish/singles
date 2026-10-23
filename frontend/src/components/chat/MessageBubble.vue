<script setup lang="ts">
import { computed, ref } from 'vue'
import { RotateCcw, Trash2 } from 'lucide-vue-next'

const props = defineProps<{
  role: 'user' | 'assistant'
  content: string
  time?: string
  avatarName?: string
  avatarUrl?: string | null
  userAvatarUrl?: string | null
  contentType?: string
  metadata?: Record<string, any> | null
  messageId?: string
  index?: number
  isLast?: boolean
}>()

const emit = defineEmits<{
  recall: [id: string]
  retry: [id: string]
}>()

const showActions = ref(false)

const cleanContent = computed(() => {
  return props.content?.replace(/\[image[:：].*?\]/gis, '').trim() || ''
})

const hasText = computed(() => {
  // A lone bracketed token such as [Image] is an image-only placeholder, not text.
  return cleanContent.value && !/^\[[^\]]+\]$/.test(cleanContent.value)
})
</script>

<template>
  <div class="message" :class="role">
    <!-- AI avatar (left side, normal flow) -->
    <div class="msg-avatar ai-avatar" v-if="role === 'assistant'">
      <img v-if="avatarUrl" :src="avatarUrl" class="avatar-img" alt="" />
      <span v-else>{{ avatarName || '?' }}</span>
    </div>

    <!-- User avatar (row-reverse flips it to the right side) -->
    <div class="msg-avatar user-avatar" v-if="role === 'user'">
      <img v-if="userAvatarUrl" :src="userAvatarUrl" class="avatar-img" alt="" />
      <span v-else>Me</span>
    </div>

    <div class="msg-content" @mouseenter="showActions = true" @mouseleave="showActions = false">
      <div class="msg-bubble" :class="role">
        <img
          v-if="contentType === 'image' && (metadata?.image_base64 || metadata?.image_url)"
          :src="metadata.image_base64 || metadata.image_url"
          class="msg-image"
          alt="Shared photo"
        />
        <span v-if="hasText" class="msg-text">{{ cleanContent }}</span>
      </div>
      <div class="msg-meta" :class="role">
        <span class="msg-time" v-if="time">{{ time }}</span>
        <div v-if="showActions && messageId" class="msg-actions" :class="role">
          <button v-if="role === 'user'" class="act-btn" title="Recall" @click.stop="emit('recall', messageId!)">
            <Trash2 :size="12" />
          </button>
          <button v-if="role === 'assistant' && isLast" class="act-btn retry" title="Ask again" @click.stop="emit('retry', messageId!)">
            <RotateCcw :size="12" />
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message {
  display: flex;
  gap: 10px;
  max-width: 75%;
  animation: msgIn 220ms var(--ease-smooth);
}
.message.user {
  align-self: flex-end;
  flex-direction: row-reverse;
}
.message.assistant {
  align-self: flex-start;
}

/* ── Avatar ── */
/* Flat identity fields, the same pair the home roster uses. */
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
  overflow: hidden;
}
.ai-avatar {
  background: var(--color-bubble-ai);
  color: var(--color-bubble-ai-ink);
}
.user-avatar {
  background: var(--color-sakura);
  color: var(--color-primary-dark);
  font-size: 12px;
}
.avatar-img {
  width: 100%;
  height: 100%;
  border-radius: inherit;
  object-fit: cover;
}

/* ── Bubble ── */
.msg-bubble {
  padding: 12px 16px;
  border-radius: 10px;
  font-size: 16px;
  line-height: 1.55;
  word-break: break-word;
  font-family: var(--font-body);
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.msg-bubble.user {
  background: var(--color-bubble-user-solid);
  color: #fff;
}
.msg-bubble.assistant {
  background: var(--color-bubble-ai);
  color: var(--color-text);
}

/* ── Image ── */
.msg-image {
  max-width: 240px;
  max-height: 200px;
  border-radius: var(--radius-sm);
  object-fit: cover;
}

/* ── Meta ── */
.msg-meta {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 3px;
  padding: 0 2px;
}
.msg-meta.user {
  justify-content: flex-end;
}
.msg-meta.assistant {
  justify-content: flex-start;
}
.msg-time {
  font-size: 12px;
  font-family: var(--font-body);
  color: var(--color-text-secondary);
}

.msg-actions {
  display: flex;
  gap: 2px;
  margin-left: 4px;
}
.msg-actions.user { justify-content: flex-end; }
.act-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px; height: 24px;
  border: none; border-radius: 10px;
  background: var(--color-sakura);
  color: var(--color-text-muted);
  cursor: pointer;
  transition: all var(--duration-fast);
}
.act-btn:hover { background: var(--color-sakura-light); color: var(--color-text); }
.act-btn.retry:hover { background: var(--color-action); color: #fff; }

@keyframes msgIn {
  from { opacity: 0; transform: translateY(4px); }
  to   { opacity: 1; transform: translateY(0); }
}

@media (prefers-reduced-motion: reduce) {
  .message { animation: none; }
}

@media (max-width: 768px) {
  .message {
    max-width: 88%;
  }
  .msg-bubble {
    font-size: 14px;
    padding: 8px 12px;
  }
  .msg-image {
    max-width: 180px;
    max-height: 150px;
  }
}
</style>
