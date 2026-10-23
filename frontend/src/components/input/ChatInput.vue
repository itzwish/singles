<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Send, Image as ImageIcon, Smile } from 'lucide-vue-next'
import { useImageUpload } from '@/composables/useImageUpload'
import EmojiPicker from './EmojiPicker.vue'
import ImagePreviewTag from './ImagePreviewTag.vue'

const emit = defineEmits<{
  send: [message: string, image: string | null]
}>()

const isMobile = /Mobi|Android|iPhone/i.test(navigator.userAgent)

const text = ref('')
const { selectedImage, previewUrl, fileInput, selectFile, onFileSelected, onPaste, clearImage } = useImageUpload()

const showQuickActions = ref(false)
const showEmoji = ref(false)
const emojiArea = ref<HTMLElement | null>(null)
const textareaRef = ref<HTMLTextAreaElement | null>(null)

function insertEmoji(emoji: string) {
  const el = textareaRef.value
  if (!el) return
  const start = el.selectionStart
  const end = el.selectionEnd
  text.value = text.value.slice(0, start) + emoji + text.value.slice(end)
  // Restore the caret position after Vue has patched the DOM
  requestAnimationFrame(() => {
    const pos = start + emoji.length
    el.focus()
    el.setSelectionRange(pos, pos)
  })
}

function toggleEmoji() {
  showEmoji.value = !showEmoji.value
}

function onEmojiSelect(emoji: string) {
  insertEmoji(emoji)
}

function onClickOutside(e: MouseEvent) {
  if (emojiArea.value && !emojiArea.value.contains(e.target as Node)) {
    showEmoji.value = false
  }
}

onMounted(() => document.addEventListener('click', onClickOutside))
onUnmounted(() => document.removeEventListener('click', onClickOutside))

const quickActions = ['I miss you', 'What are you up to?', "What's fun today?"]

const canSend = computed(() => text.value.trim().length > 0 || selectedImage.value !== null)

function onQuickAction(msg: string) {
  emit('send', msg, null)
  showQuickActions.value = false
}

function onSubmit() {
  if (!canSend.value) return
  emit('send', text.value.trim(), selectedImage.value)
  text.value = ''
  clearImage()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey && !isMobile) {
    e.preventDefault()
    onSubmit()
  }
}
</script>

<template>
  <div class="chat-input-area">
    <!-- Image preview -->
    <ImagePreviewTag v-if="previewUrl" :url="previewUrl" @remove="clearImage" />

    <!-- Quick replies -->
    <div v-if="showQuickActions" class="quick-actions">
      <button
        v-for="qa in quickActions"
        :key="qa"
        type="button"
        class="qa-chip"
        @click="onQuickAction(qa)"
      >
        {{ qa }}
      </button>
    </div>

    <!-- Input row -->
    <div class="input-row">
      <div class="emoji-area" ref="emojiArea">
        <button class="tool-btn" @click="toggleEmoji" title="Emoji">
          <Smile :size="20" />
        </button>
        <EmojiPicker v-if="showEmoji" class="emoji-popover" @select="onEmojiSelect" />
      </div>

      <button class="tool-btn" @click="selectFile" title="Send a photo">
        <ImageIcon :size="20" />
      </button>
      <input
        type="file"
        ref="fileInput"
        accept="image/*"
        hidden
        @change="onFileSelected"
      />

      <div class="input-wrapper">
        <textarea
          ref="textareaRef"
          v-model="text"
          class="input-field"
          rows="1"
          placeholder="Write a message..."
          maxlength="2000"
          @keydown="onKeydown"
          @paste="onPaste"
        />
      </div>

      <button
        class="send-btn"
        :class="{ ready: canSend }"
        :disabled="!canSend"
        @click="onSubmit"
      >
        <Send :size="20" />
      </button>
    </div>

    <div class="input-footer">
      <button type="button" class="qa-toggle" @click="showQuickActions = !showQuickActions">
        {{ showQuickActions ? 'Hide' : 'Quick replies' }}
      </button>
      <div v-if="isMobile" class="input-hint">Tap the send button</div>
      <div v-else class="input-hint">Enter sends · Shift + Enter adds a line</div>
    </div>
  </div>
</template>

<style scoped>
.chat-input-area {
  flex-shrink: 0;
  padding: 12px 20px 14px;
  background: var(--color-surface);
  border-top: 1px solid var(--color-border);
}

.input-row {
  display: flex;
  align-items: flex-end;
  gap: 8px;
}

.tool-btn {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-xs);
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--color-text-secondary);
  background: transparent;
  border: 1px solid var(--color-border);
  flex-shrink: 0;
  cursor: pointer;
  transition: background-color 140ms var(--ease-smooth), color 140ms var(--ease-smooth);
}
.tool-btn:hover {
  background: var(--color-sakura);
  color: var(--color-text);
}
.tool-btn:focus-visible {
  outline: 2px solid var(--color-action);
  outline-offset: 2px;
}

.input-wrapper {
  flex: 1;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  transition: border-color 140ms var(--ease-smooth);
  overflow: hidden;
}
.input-wrapper:focus-within {
  border-color: var(--color-primary);
}

.input-field {
  width: 100%;
  resize: none;
  border: none;
  padding: 10px 14px;
  font-size: 16px;
  font-family: var(--font-body);
  line-height: 1.6;
  outline: none;
  background: transparent;
  color: var(--color-text);
  max-height: 120px;
}
.input-field::placeholder {
  color: var(--color-text-muted);
  font-weight: 400;
}

.send-btn {
  width: 38px;
  height: 38px;
  border-radius: var(--radius-xs);
  flex-shrink: 0;
  background: var(--color-surface);
  color: var(--color-text-muted);
  border: 1px solid var(--color-border);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background-color 140ms var(--ease-smooth), color 140ms var(--ease-smooth);
}
.send-btn:hover:not(:disabled) {
  background: var(--color-sakura);
  color: var(--color-text);
}
.send-btn.ready {
  background: var(--color-action);
  color: #fff;
  border-color: var(--color-action);
}
.send-btn.ready:hover {
  background: var(--color-action-hover);
  color: #fff;
}
.send-btn:disabled {
  cursor: not-allowed;
}
.send-btn:focus-visible {
  outline: 2px solid var(--color-action);
  outline-offset: 2px;
}

/* ── Quick actions ── */
.quick-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}

.qa-chip {
  padding: 6px 12px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  font-size: 13px;
  font-family: var(--font-body);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: border-color 140ms var(--ease-smooth), color 140ms var(--ease-smooth);
}
.qa-chip:hover {
  border-color: var(--color-primary);
  color: var(--color-text);
  background: var(--color-sakura);
}

.input-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-top: 6px;
  padding-right: 4px;
}

.qa-toggle {
  border: none;
  background: none;
  font-size: 12px;
  font-family: var(--font-body);
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 2px 4px;
  border-radius: var(--radius-xs);
  transition: color 140ms var(--ease-smooth);
}
.qa-toggle:hover {
  color: var(--color-text);
}

.input-hint {
  font-size: 12px;
  font-family: var(--font-body);
  color: var(--color-text-secondary);
}

/* ── Emoji ── */
.emoji-area {
  position: relative;
}
.emoji-popover {
  position: absolute;
  bottom: 48px;
  left: 0;
  z-index: 100;
}

@media (max-width: 768px) {
  .chat-input-area {
    padding: 8px 12px 10px;
    padding-bottom: max(10px, env(safe-area-inset-bottom));
  }
  .input-row {
    gap: 6px;
  }
  .tool-btn {
    width: 36px;
    height: 36px;
  }
  .send-btn {
    width: 36px;
    height: 36px;
  }
  .input-field {
    font-size: 16px;
    padding: 9px 12px;
  }
  .quick-actions {
    gap: 4px;
  }
  .qa-chip {
    font-size: 13px;
    padding: 5px 10px;
  }
}

@media (max-width: 480px) {
  .chat-input-area {
    padding: 8px 10px 10px;
    padding-bottom: max(10px, env(safe-area-inset-bottom));
  }
  .input-row {
    gap: 6px;
  }
  .tool-btn {
    width: 36px;
    height: 36px;
  }
  .send-btn {
    width: 36px;
    height: 36px;
  }
  .input-field {
    font-size: 14px;
    padding: 9px 12px;
  }
}
</style>
