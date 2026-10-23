<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import TopBar from '@/components/layout/TopBar.vue'
import CharacterCard from '@/components/shared/CharacterCard.vue'
import CreateCharacterForm from '@/components/shared/CreateCharacterForm.vue'
import BaseModal from '@/components/shared/BaseModal.vue'
import GuideModal from '@/components/shared/GuideModal.vue'
import type { Character } from '@/types/models'

const router = useRouter()
const chat = useChatStore()
const auth = useAuthStore()
const { characters } = storeToRefs(chat)

const loading = ref(true)
const loadError = ref('')
const showCreateModal = ref(false)
const creating = ref(false)

// Delete confirmation
const charToDelete = ref<Character | null>(null)
const showDeleteModal = computed(() => charToDelete.value !== null)
const deleting = ref(false)
const deleteError = ref('')

// New-user guide
const showGuide = ref(false)

onMounted(async () => {
  await loadRoster()
  await auth.loadUserInfo()
  if (!localStorage.getItem('guide_read')) {
    showGuide.value = true
  }
})

async function loadRoster() {
  loading.value = true
  loadError.value = ''
  try {
    await chat.loadCharacters()
  } catch {
    loadError.value = "Couldn't load your companions."
  } finally {
    loading.value = false
  }
}

/** The roster's shape decides the grid: three across, two, or one with the builder beside her. */
const rosterCount = computed(() => Math.min(characters.value.length, 3))

/** The line under the title names who is here, built from the roster itself. */
const introLine = computed(() => {
  const names = characters.value.map((c) => c.name)
  if (names.length === 0) return 'Nobody here yet. Build the first companion and she is waiting for you.'
  if (names.length === 1) return `${names[0]} is here, and she remembers where you left off.`
  const last = names[names.length - 1]
  return `${names.slice(0, -1).join(', ')} and ${last} each keep their own memory of what you tell them.`
})

async function onSelectCharacter(characterId: string) {
  router.push(`/chat/${characterId}`)
}

function onDeleteRequest(char: Character) {
  charToDelete.value = char
  deleteError.value = ''
}

async function confirmDelete() {
  if (!charToDelete.value) return
  deleting.value = true
  deleteError.value = ''
  try {
    await chat.deleteCharacter(charToDelete.value.id)
    charToDelete.value = null
  } catch (e: any) {
    deleteError.value = e?.response?.data?.detail || e?.message || 'Delete failed. Please try again.'
  } finally {
    deleting.value = false
  }
}

function cancelDelete() {
  charToDelete.value = null
  deleteError.value = ''
}

async function onCreateCharacter(data: { name: string; description: string; system_prompt: string; personality_profile: Record<string, any> | null; files: File[]; avatarFile: File | null }) {
  creating.value = true
  try {
    const char = await chat.createCharacter({
      name: data.name,
      description: data.description,
      system_prompt: data.system_prompt,
      personality_profile: data.personality_profile,
    })
    if (data.avatarFile) {
      await chat.uploadAvatar(char.id, data.avatarFile)
    }
    if (data.files.length > 0) {
      await chat.uploadCharacterDocuments(char.id, data.files)
    }
    showCreateModal.value = false
    router.push(`/chat/${char.id}`)
  } catch (e) {
    console.error('Failed to create character:', e)
  } finally {
    creating.value = false
  }
}
</script>

<template>
  <div class="home-view">
    <TopBar />

    <main class="canvas">
      <div class="column">
        <header class="intro">
          <h1 class="intro-title">Who are you talking to?</h1>
          <p class="intro-line">{{ introLine }}</p>
        </header>

        <p v-if="loading" class="state" aria-live="polite">Gathering your companions…</p>

        <p v-else-if="loadError" class="state" aria-live="polite">
          {{ loadError }}
          <button class="state-action" type="button" @click="loadRoster">Try again</button>
        </p>

        <div v-else class="grid" :class="`n${rosterCount}`">
          <CharacterCard
            v-for="(char, index) in characters"
            :key="char.id"
            :character="char"
            :tone="index"
            @select="onSelectCharacter(char.id)"
            @delete-request="onDeleteRequest(char)"
          />

          <section class="build-panel">
            <div class="build-copy">
              <h2 class="build-title">Build your own</h2>
              <p class="build-line">
                A name, a temperament, the way she talks. She keeps all of it, and she keeps you in mind.
              </p>
            </div>
            <button class="build-action" type="button" @click="showCreateModal = true">
              Create a character
            </button>
          </section>
        </div>
      </div>
    </main>

    <!-- Create character modal -->
    <BaseModal :show="showCreateModal" title="Create a new character" :closeOnOverlay="false" @close="showCreateModal = false">
      <CreateCharacterForm
        :disabled="creating"
        @submit="onCreateCharacter"
        @cancel="showCreateModal = false"
      />
    </BaseModal>

    <!-- Delete confirmation modal -->
    <BaseModal :show="showDeleteModal" title="Delete character" @close="cancelDelete">
      <p class="delete-confirm-text">
        Really leaving <strong>{{ charToDelete?.name }}</strong>? (´；ω；`)
      </p>
      <p class="delete-confirm-hint">Delete them and they're gone for good… all the memories go with them… please don't leave me like this (⋟﹏⋞</p>
      <p v-if="deleteError" class="delete-error">{{ deleteError }}</p>
      <template #footer>
        <button class="btn btn-cancel" @click="cancelDelete" :disabled="deleting">Keep</button>
        <button class="btn btn-delete" @click="confirmDelete" :disabled="deleting">
          {{ deleting ? 'Deleting...' : 'Delete anyway' }}
        </button>
      </template>
    </BaseModal>

    <!-- New-user guide -->
    <GuideModal v-if="showGuide" @close="showGuide = false" />
  </div>
</template>

<style scoped>
.home-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

/* One gutter, one column: the header and every panel share the same edges. */
.canvas {
  flex: 1;
  overflow-y: auto;
  padding: 56px 32px 72px;
}

.column {
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
}

/* ── Intro ── */
.intro {
  margin-bottom: 36px;
}

.intro-title {
  font-family: var(--font-heading);
  font-size: 32px;
  font-weight: 400;
  line-height: 1.1;
  color: var(--color-text);
  letter-spacing: -0.01em;
}

.intro-line {
  margin-top: 12px;
  max-width: 62ch;
  font-size: 16px;
  line-height: 1.55;
  color: var(--color-text-secondary);
}

/* ── Grid: 12 x 77px + 11 x 16px = 1100px ── */
.grid {
  display: grid;
  grid-template-columns: repeat(12, minmax(0, 1fr));
  gap: 16px;
}

.grid :deep(.char-panel) {
  grid-column: span 4;
}
.grid.n2 :deep(.char-panel) {
  grid-column: span 6;
}
.grid.n1 :deep(.char-panel) {
  grid-column: span 6;
}

/* ── Build panel ── */
.build-panel {
  grid-column: span 12;
  margin-top: 16px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 32px;
  padding: 28px 32px;
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
}
.grid.n1 .build-panel {
  grid-column: span 6;
  flex-direction: column;
  align-items: flex-start;
  justify-content: space-between;
  gap: 24px;
}

.build-copy {
  min-width: 0;
}

.build-title {
  font-family: var(--font-heading);
  font-size: 20px;
  letter-spacing: 0;
  font-weight: 600;
  line-height: 1.25;
  color: var(--color-text);
}

.build-line {
  margin-top: 6px;
  max-width: 52ch;
  font-size: 14px;
  line-height: 1.55;
  color: var(--color-text-secondary);
}

.build-action {
  flex-shrink: 0;
  padding: 11px 20px;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--color-action);
  color: var(--color-text-inverse);
  font-family: var(--font-body);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 140ms var(--ease-smooth);
}
.build-action:hover {
  background: var(--color-action-hover);
}
.build-action:focus-visible {
  outline: 2px solid var(--color-action);
  outline-offset: 2px;
}

/* ── States ── */
.state {
  grid-column: span 12;
  padding: 28px 0;
  font-size: 15px;
  color: var(--color-text-secondary);
}
.state-action {
  margin-left: 6px;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--color-primary-dark);
  font-size: 15px;
  font-weight: 600;
  text-decoration: underline;
  text-underline-offset: 3px;
  cursor: pointer;
}

/* ── Delete confirmation modal ── */
.delete-confirm-text {
  font-size: var(--text-sm);
  color: var(--color-text);
  line-height: 1.6;
  margin-bottom: 8px;
}
.delete-confirm-hint {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}
.delete-error {
  margin-top: 10px;
  padding: 8px 12px;
  background: rgba(232,128,138,0.1);
  border: 1px solid rgba(232,128,138,0.2);
  border-radius: var(--radius-xs);
  font-size: var(--text-xs);
  color: var(--color-error);
}

.btn {
  padding: 8px 20px;
  border: none;
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  font-weight: 500;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-cancel {
  background: var(--color-bg);
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
}
.btn-cancel:hover:not(:disabled) {
  background: var(--color-sakura-light);
}
.btn-delete {
  background: var(--color-error);
  color: #fff;
}
.btn-delete:hover:not(:disabled) {
  background: #c0392b;
}

@media (max-width: 1024px) {
  .canvas {
    padding: 40px 24px 56px;
  }
  .intro-title {
    font-size: 30px;
  }
}

@media (max-width: 640px) {
  .canvas {
    padding: 28px 16px 48px;
  }
  .intro {
    margin-bottom: 24px;
  }
  .intro-title {
    font-size: 24px;
  }
  .intro-line {
    margin-top: 8px;
    font-size: 15px;
  }
  .grid {
    gap: 12px;
  }
  .grid :deep(.char-panel),
  .grid.n2 :deep(.char-panel),
  .grid.n1 :deep(.char-panel) {
    grid-column: span 12;
  }
  .grid.n1 .build-panel {
    grid-column: span 12;
  }
  .build-panel {
    flex-direction: column;
    align-items: flex-start;
    gap: 18px;
    padding: 22px 20px;
  }
  .build-action {
    width: 100%;
    text-align: center;
  }
}

@media (prefers-reduced-motion: reduce) {
  .build-action {
    transition: none;
  }
}
</style>
