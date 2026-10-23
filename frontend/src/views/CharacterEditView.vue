<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { ArrowLeft, Save, RotateCcw } from 'lucide-vue-next'

const props = defineProps<{ characterId: string }>()
const router = useRouter()
const chat = useChatStore()

const loading = ref(true)
const saving = ref(false)
const error = ref('')

// Basics
const name = ref('')
const description = ref('')

// Persona fields
const task = ref('')
const appearance = ref('')
const background = ref('')
const personality = ref('')
const speakingStyle = ref('')
const preferences = ref('')
const outputExamples = ref('')
const behavioralRules = ref('')

// expression_style arrays
const exprConfirm = ref('')
const exprApologize = ref('')
const exprThanks = ref('')
const exprPetNames = ref('')
const exprEmoji = ref('')

interface ProfileData {
  name?: string
  description?: string
  personality_profile?: Record<string, any> | null
}

function loadProfile() {
  loading.value = true
  let char = chat.characters.find(c => c.id === props.characterId)
  if (!char) {
    error.value = 'Character not found'
    loading.value = false
    return
  }
  const profile = char.personality_profile
  name.value = char.name || ''
  description.value = char.description || ''
  if (profile) {
    task.value = profile.task || ''
    appearance.value = profile.appearance || ''
    background.value = profile.background || ''
    personality.value = profile.personality || ''
    speakingStyle.value = profile.speaking_style || ''
    preferences.value = profile.preferences || ''
    outputExamples.value = profile.output_examples || ''
    behavioralRules.value = profile.behavioral_rules || ''

    const expr = profile.expression_style || {}
    exprConfirm.value = (expr.confirm || []).join(', ')
    exprApologize.value = (expr.apologize || []).join(', ')
    exprThanks.value = (expr.thanks || []).join(', ')
    exprPetNames.value = (expr.pet_names || []).join(', ')
    exprEmoji.value = (expr.emoji || []).join('')
  }
  loading.value = false
}

function parseExpr(val: string): string[] {
  return val.split(/[，,、]/).map(s => s.trim()).filter(Boolean)
}

async function save() {
  saving.value = true
  try {
    const profile: Record<string, any> = {
      task: task.value,
      appearance: appearance.value,
      background: background.value,
      personality: personality.value,
      speaking_style: speakingStyle.value,
      expression_style: {
        confirm: parseExpr(exprConfirm.value),
        apologize: parseExpr(exprApologize.value),
        thanks: parseExpr(exprThanks.value),
        pet_names: parseExpr(exprPetNames.value),
        emoji: parseExpr(exprEmoji.value).join('').split(''),
      },
      preferences: preferences.value,
      output_examples: outputExamples.value,
      behavioral_rules: behavioralRules.value,
    }
    await chat.updateCharacter(props.characterId, {
      name: name.value,
      description: description.value,
      personality_profile: profile,
    })
  } finally {
    saving.value = false
  }
}

function goBack() {
  router.back()
}

onMounted(() => {
  if (!chat.characters.length) {
    chat.loadCharacters().then(loadProfile)
  } else {
    loadProfile()
  }
})
</script>

<template>
  <div class="edit-view">
    <header class="edit-header">
      <button class="back-btn" @click="goBack">
        <ArrowLeft :size="20" />
      </button>
      <h1>Tune character</h1>
      <button class="save-btn" :disabled="saving" @click="save">
        <Save :size="16" />
        <span>{{ saving ? 'Saving...' : 'Save' }}</span>
      </button>
    </header>

    <div v-if="error" class="edit-error">{{ error }}</div>

    <main v-if="!loading && !error" class="edit-main">
      <!-- Basics -->
      <section class="edit-section">
        <h2 class="section-title">Basics</h2>
        <label class="field">
          <span>Name</span>
          <input v-model="name" class="field-input" />
        </label>
        <label class="field">
          <span>Short bio</span>
          <input v-model="description" class="field-input" />
        </label>
      </section>

      <!-- Persona -->
      <section class="edit-section">
        <h2 class="section-title">Persona</h2>
        <label class="field">
          <span>Role</span>
          <textarea v-model="task" class="field-area" rows="3" />
        </label>
        <label class="field">
          <span>Appearance</span>
          <textarea v-model="appearance" class="field-area" rows="3" />
        </label>
        <label class="field">
          <span>Background</span>
          <textarea v-model="background" class="field-area" rows="4" />
        </label>
        <label class="field">
          <span>Personality</span>
          <textarea v-model="personality" class="field-area" rows="4" />
        </label>
        <label class="field">
          <span>Speaking style</span>
          <textarea v-model="speakingStyle" class="field-area" rows="3" />
        </label>
      </section>

      <!-- Expression style -->
      <section class="edit-section">
        <h2 class="section-title">Expression style</h2>
        <p class="section-hint">Separate multiple entries with commas</p>
        <label class="field">
          <span>When agreeing</span>
          <input v-model="exprConfirm" class="field-input" placeholder="Sure, Got it, Sounds good" />
        </label>
        <label class="field">
          <span>When apologizing</span>
          <input v-model="exprApologize" class="field-input" placeholder="Sorry, My bad" />
        </label>
        <label class="field">
          <span>When thanking</span>
          <input v-model="exprThanks" class="field-input" placeholder="Thanks, Thank you" />
        </label>
        <label class="field">
          <span>Nicknames for you</span>
          <input v-model="exprPetNames" class="field-input" placeholder="babe, sweetheart" />
        </label>
        <label class="field">
          <span>Favourite emoji</span>
          <input v-model="exprEmoji" class="field-input" placeholder="😊💕✨" />
        </label>
      </section>

      <!-- Extra -->
      <section class="edit-section">
        <h2 class="section-title">Extra</h2>
        <label class="field">
          <span>Preferences</span>
          <textarea v-model="preferences" class="field-area" rows="3" />
        </label>
        <label class="field">
          <span>Sample replies</span>
          <p class="section-hint">Separate samples with \</p>
          <textarea v-model="outputExamples" class="field-area" rows="3" />
        </label>
        <label class="field">
          <span>Rules</span>
          <textarea v-model="behavioralRules" class="field-area" rows="5" />
        </label>
      </section>
    </main>
  </div>
</template>

<style scoped>
.edit-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}
.edit-header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--color-border);
  background: var(--color-bg);
  position: sticky;
  top: 0;
  z-index: 10;
}
.edit-header h1 {
  flex: 1;
  font-size: 18px;
  font-weight: 700;
  font-family: var(--font-heading);
  color: var(--color-text);
  margin: 0;
}
.back-btn {
  display: flex;
  align-items: center;
  padding: 4px;
  border: none;
  background: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: var(--radius-xs);
}
.back-btn:hover { color: var(--color-text); }
.save-btn {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-primary);
  color: #fff;
  font-size: var(--text-sm);
  font-family: var(--font-body);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast);
}
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.save-btn:hover:not(:disabled) { opacity: 0.9; }
.edit-error {
  padding: 60px 24px;
  text-align: center;
  color: var(--color-error);
  font-size: var(--text-sm);
}
.edit-main {
  flex: 1;
  overflow-y: auto;
  padding: 20px 16px 40px;
  display: flex;
  flex-direction: column;
  gap: 24px;
}
.edit-section {
  background: var(--color-surface);
  border-radius: var(--radius-md);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.section-title {
  font-size: 15px;
  font-weight: 700;
  font-family: var(--font-heading);
  color: var(--color-text);
  margin: 0;
}
.section-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  margin: -8px 0 0;
}
.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.field span {
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-text-secondary);
  font-family: var(--font-body);
}
.field-input {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  color: var(--color-text);
  background: var(--color-bg);
  outline: none;
  transition: border-color var(--duration-fast);
}
.field-input:focus { border-color: var(--color-primary); }
.field-area {
  padding: 8px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  color: var(--color-text);
  background: var(--color-bg);
  outline: none;
  resize: vertical;
  line-height: 1.6;
  transition: border-color var(--duration-fast);
}
.field-area:focus { border-color: var(--color-primary); }
</style>
