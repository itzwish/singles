<script setup lang="ts">
/**
 * One companion in the home roster.
 *
 * The panel's tone is her identity: a pale field of her own hue with a deep
 * ink of the same hue for the initial and her traits. Identity, not data —
 * the tints stay out of any legend and never carry meaning on their own.
 */
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ArrowRight, Camera, Pencil, Trash2 } from 'lucide-vue-next'
import type { Character } from '@/types/models'
import { useChatStore } from '@/stores/chat'

const props = defineProps<{
  character: Character
  tone: number
}>()

const emit = defineEmits<{
  select: []
  deleteRequest: []
}>()

const router = useRouter()
const chat = useChatStore()
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const avatarVersion = ref(0)

/** Three hues at least 60 degrees apart, all inside the brand's sakura family. */
const TONES = [
  { field: '#FFE9F0', edge: '#FFCFDF', ink: '#A83D68' },
  { field: '#EFE8FF', edge: '#DACCFA', ink: '#61449F' },
  { field: '#E9F2E7', edge: '#D2E5CE', ink: '#3E6A43' },
]

const tone = computed(() => TONES[((props.tone % TONES.length) + TONES.length) % TONES.length])

const panelStyle = computed(() => ({
  '--panel-field': tone.value.field,
  '--panel-edge': tone.value.edge,
  '--panel-ink': tone.value.ink,
}))

const avatarSrc = computed(() =>
  props.character.avatar_url ? `${props.character.avatar_url}?v=${avatarVersion.value}` : '',
)

/** Personality keywords, without the emoji the profiles also carry. */
const traits = computed(() => {
  const raw = props.character.personality_profile?.personality || ''
  return raw
    .split(/[,.;]/)
    .map((part) => part.trim())
    .filter((part) => part.length > 0 && part.length < 24)
    .slice(0, 2)
})

function triggerUpload() {
  fileInput.value?.click()
}

async function onFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    await chat.uploadAvatar(props.character.id, file)
    avatarVersion.value++
  } catch {
    // The next upload attempt is the retry; nothing else to tell the user here.
  } finally {
    uploading.value = false
    target.value = ''
  }
}
</script>

<template>
  <article class="char-panel" :style="panelStyle">
    <button
      class="portrait"
      type="button"
      :aria-label="`Open the chat with ${character.name}`"
      @click="emit('select')"
    >
      <img v-if="character.avatar_url" :src="avatarSrc" :alt="character.name" class="portrait-img" />
      <span v-else class="initial" aria-hidden="true">{{ character.name.charAt(0) }}</span>
    </button>

    <div class="panel-body">
      <h2 class="char-name">{{ character.name }}</h2>
      <p class="char-desc">{{ character.description || 'No description written yet.' }}</p>
      <p v-if="traits.length" class="char-traits">{{ traits.join(' · ') }}</p>
    </div>

    <div class="panel-foot">
      <button class="start" type="button" @click="emit('select')">
        Start chat
        <ArrowRight :size="15" aria-hidden="true" />
      </button>

      <div class="tools">
        <button
          class="tool"
          type="button"
          title="Change photo"
          aria-label="Change photo"
          :disabled="uploading"
          @click="triggerUpload"
        >
          <Camera :size="15" aria-hidden="true" />
        </button>
        <button
          class="tool"
          type="button"
          title="Tune her persona"
          aria-label="Tune her persona"
          @click="router.push(`/character/${character.id}/edit`)"
        >
          <Pencil :size="15" aria-hidden="true" />
        </button>
        <button
          v-if="!character.is_template"
          class="tool"
          type="button"
          title="Delete her"
          aria-label="Delete her"
          @click="emit('deleteRequest')"
        >
          <Trash2 :size="15" aria-hidden="true" />
        </button>
      </div>
    </div>

    <input
      ref="fileInput"
      type="file"
      accept="image/jpeg,image/png,image/webp,image/gif"
      class="file-input"
      @change="onFileChange"
    />
  </article>
</template>

<style scoped>
.char-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  background: var(--panel-field);
  border: 1px solid var(--panel-edge);
  border-radius: var(--radius);
  overflow: hidden;
  transition:
    border-color 160ms var(--ease-smooth),
    background-color 160ms var(--ease-smooth);
}
.char-panel:hover {
  border-color: var(--panel-ink);
}

/* ── Portrait ── */
.portrait {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  aspect-ratio: 4 / 3;
  padding: 0;
  border: 0;
  background: transparent;
  cursor: pointer;
  overflow: hidden;
}
.portrait-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}
.initial {
  font-family: var(--font-heading);
  font-size: 84px;
  line-height: 1;
  color: var(--panel-ink);
  transition: transform 240ms var(--ease-smooth);
}
.portrait:hover .initial {
  transform: scale(1.03);
}

/* ── Copy ── */
.panel-body {
  padding: 0 20px 18px;
}
.char-name {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 600;
  line-height: 1.2;
  color: var(--color-text);
}
.char-desc {
  /* Three lines whether she needs them or not: the row shares one foot line. */
  min-height: 4.65em;
  margin-top: 6px;
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text-secondary);
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.char-traits {
  margin-top: 10px;
  font-size: 14px;
  line-height: 1.4;
  color: var(--panel-ink);
}

/* ── Foot ── */
.panel-foot {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: auto;
  padding: 10px 12px 10px 20px;
  border-top: 1px solid var(--panel-edge);
}
.start {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 0;
  font-family: var(--font-body);
  font-size: 14px;
  font-weight: 600;
  color: var(--color-text);
  cursor: pointer;
  transition: color 140ms var(--ease-smooth);
}
.start:hover {
  color: var(--panel-ink);
}
.start :deep(svg) {
  transition: transform 200ms var(--ease-smooth);
}
.start:hover :deep(svg) {
  transform: translateX(2px);
}

.tools {
  display: flex;
  align-items: center;
  gap: 2px;
}
.tool {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-xs);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition:
    background-color 140ms var(--ease-smooth),
    color 140ms var(--ease-smooth);
}
.tool:hover {
  background: rgba(255, 255, 255, 0.75);
  color: var(--color-text);
}
.tool:disabled {
  opacity: 0.45;
  cursor: default;
}

.file-input {
  display: none;
}

/* ── Focus ── */
.portrait:focus-visible,
.start:focus-visible,
.tool:focus-visible {
  outline: 2px solid var(--panel-ink);
  outline-offset: 2px;
  border-radius: var(--radius-xs);
}

@media (max-width: 768px) {
  .initial {
    font-size: 64px;
  }
  .panel-body {
    padding: 0 16px 14px;
  }
  .char-name {
    font-size: 18px;
  }
  .panel-foot {
    padding: 8px 10px 8px 16px;
  }
}

@media (prefers-reduced-motion: reduce) {
  .char-panel,
  .initial,
  .start,
  .start :deep(svg),
  .tool {
    transition: none;
  }
}
</style>
