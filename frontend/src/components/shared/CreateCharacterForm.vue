<script setup lang="ts">
import { ref, computed } from 'vue'
import { Sparkles, ChevronLeft, Brain, MessageSquareText, Camera } from 'lucide-vue-next'
import { useChatStore } from '@/stores/chat'
import { useAuthStore } from '@/stores/auth'
import type { PersonalityProfile } from '@/types/models'

const emit = defineEmits<{
  submit: [data: { name: string; description: string; system_prompt: string; personality_profile: Record<string, any> | null; files: File[]; avatarFile: File | null }]
  cancel: []
}>()

const chat = useChatStore()
const auth = useAuthStore()

// null = pick a method, 'describe' = describe & generate, 'chat' = import a chat log
const mode = ref<string | null>(null)
const step = ref(1)
const generating = ref(false)
const analyzing = ref(false)
const error = ref('')

// ── Shared fields ──
const name = ref('')
const description = ref('')
const profile = ref<PersonalityProfile>({})
const useAdvanced = ref(false)
const systemPrompt = ref('')

// Method one — user description
const userDescription = ref('')

// Method two — chat log import
const chatLogText = ref('')
const avatarInput = ref<HTMLInputElement | null>(null)
const avatarFile = ref<File | null>(null)
const avatarPreview = ref<string | null>(null)

const chatFileInput = ref<HTMLInputElement | null>(null)
const chatFileName = ref('')
const analysisResult = ref<Record<string, any> | null>(null)

function extractName(desc: string): string {
  // Pick up a name from free text: "named X", "called X", "her name is X".
  const match = desc.match(/\b(?:named|called|name\s+is)\s+["'‘’“”]?([^\s,.;:!?"'‘’“”]+)/i)
  return match?.[1] || ''
}

function smartSlice(text: string, max = 80): string {
  if (text.length <= max) return text
  // Look for the closest sentence end before the limit
  const truncated = text.slice(0, max)
  const m = truncated.match(/[.!?\n]/g)
  if (m) {
    const last = truncated.lastIndexOf(m[m.length - 1])
    if (last > max * 0.5) return truncated.slice(0, last + 1)
  }
  // Otherwise settle for the closest comma
  const comma = truncated.lastIndexOf(',')
  if (comma > max * 0.5) return truncated.slice(0, comma + 1)
  return truncated
}

function selectMode(m: string) {
  mode.value = m
  step.value = 1
  error.value = ''
  name.value = ''
  description.value = ''
}

function backToSelect() {
  mode.value = null
  step.value = 1
  error.value = ''
  name.value = ''
  description.value = ''
  profile.value = {}
  userDescription.value = ''
  chatLogText.value = ''
  chatFileName.value = ''
  analysisResult.value = null
  avatarFile.value = null
  avatarPreview.value = null
}

// ── Avatar ──
function triggerAvatar() {
  avatarInput.value?.click()
}

function onAvatarChange(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  avatarFile.value = file
  const reader = new FileReader()
  reader.onload = () => {
    avatarPreview.value = reader.result as string
  }
  reader.readAsDataURL(file)
  target.value = ''
}

// ══════════════════════════════════════════════
// Method one: describe & generate
// ══════════════════════════════════════════════

async function onGenerate() {
  if (!userDescription.value.trim()) {
    error.value = 'Describe the character you want first'
    return
  }
  if (!auth.hasApiKey) { auth.promptApiKey(); return }
  error.value = ''
  generating.value = true
  try {
    const result = await chat.generateCharacterProfile(userDescription.value)
    profile.value = result
    if (!name.value) {
      name.value = extractName(userDescription.value)
    }
    if (!description.value && result.personality) {
      description.value = smartSlice(result.personality)
    }
    step.value = 2
  } catch (e: any) {
    console.error('AI character generation failed:', e)
    error.value = e?.response?.data?.detail || e?.message || 'Generation failed, please try again'
  } finally {
    generating.value = false
  }
}

function onSkipToAdvanced() {
  useAdvanced.value = true
  step.value = 2
}

function doSubmitDescribe() {
  error.value = ''
  if (!name.value.trim()) {
    error.value = 'Please enter a name'
    return
  }
  if (useAdvanced.value && !systemPrompt.value.trim()) {
    error.value = 'Please enter a persona'
    return
  }
  emit('submit', {
    name: name.value.trim(),
    description: description.value.trim(),
    system_prompt: useAdvanced.value ? systemPrompt.value.trim() : '',
    personality_profile: useAdvanced.value ? null : profile.value,
    files: [],
    avatarFile: avatarFile.value,
  })
}

// ══════════════════════════════════════════════
// Method two: chat log import
// ══════════════════════════════════════════════

function triggerChatFile() {
  chatFileInput.value?.click()
}

async function onChatFileSelected(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  chatFileName.value = file.name
  const reader = new FileReader()
  reader.onload = () => {
    chatLogText.value = reader.result as string
  }
  reader.readAsText(file, 'UTF-8')
  target.value = ''
}

async function onAnalyzeChat() {
  if (!chatLogText.value.trim()) {
    error.value = 'Paste or upload a chat log first'
    return
  }
  if (!auth.hasApiKey) { auth.promptApiKey(); return }
  error.value = ''
  analyzing.value = true
  try {
    // Pass no existing profile — distil the character purely from the chat log
    const result = await chat.analyzeChatLogs(chatLogText.value, null)
    if (result.enhanced_profile) {
      analysisResult.value = result.enhanced_profile
      profile.value = result.enhanced_profile
      if (!description.value && result.enhanced_profile.personality) {
        description.value = smartSlice(result.enhanced_profile.personality)
      }
      step.value = 2
    }
  } catch (e: any) {
    console.error('Chat log analysis failed:', e)
    error.value = e?.response?.data?.detail || e?.message || 'Analysis failed, please try again'
  } finally {
    analyzing.value = false
  }
}

function doSubmitChat() {
  error.value = ''
  if (!name.value.trim()) {
    error.value = 'Please enter a name'
    return
  }
  emit('submit', {
    name: name.value.trim(),
    description: description.value.trim(),
    system_prompt: '',
    personality_profile: profile.value,
    files: [],
    avatarFile: avatarFile.value,
  })
}

const expr = computed(() => profile.value.expression_style || {})
</script>

<template>
  <form class="wizard" @submit.prevent>
    <!-- ═══════════════════════════════════════ -->
    <!-- Method select                           -->
    <!-- ═══════════════════════════════════════ -->
    <div v-if="mode === null" class="mode-select">
      <h3 class="step-title" style="text-align:center">How do you want to create her?</h3>

      <div class="mode-cards">
        <button type="button" class="mode-card" @click="selectMode('describe')">
          <div class="mode-icon"><Sparkles :size="28" /></div>
          <div class="mode-name">Describe &amp; generate</div>
          <div class="mode-desc">Describe her in your own words, AI builds the full persona</div>
        </button>

        <button type="button" class="mode-card" @click="selectMode('chat')">
          <div class="mode-icon"><MessageSquareText :size="28" /></div>
          <div class="mode-name">Import a chat log</div>
          <div class="mode-desc">Paste a chat log, AI distils her whole personality</div>
        </button>
      </div>
    </div>

    <!-- ═══════════════════════════════════════ -->
    <!-- Method one: describe & generate          -->
    <!-- ═══════════════════════════════════════ -->
    <template v-if="mode === 'describe'">
      <!-- Step indicator -->
      <div class="steps">
        <div class="step-dot" :class="{ active: step >= 1, done: step > 1 }">1</div>
        <div class="step-line" :class="{ active: step > 1 }" />
        <div class="step-dot" :class="{ active: step >= 2 }">2</div>
      </div>

      <!-- Step 1: describe her -->
      <div v-if="step === 1" class="step-content">
        <h3 class="step-title">Describe your character</h3>
        <p class="step-desc">Tell AI what you want her to be — the more detail the better. Age, personality, relationship, backstory, and so on.</p>

        <textarea
          v-model="userDescription"
          class="desc-textarea"
          rows="5"
          placeholder="e.g. A 20-year-old college student, sweet and playful, my girlfriend. She loves cooking and anime, speaks softly, and acts a little spoiled. We've been together since university..."
          maxlength="500"
        />
        <div class="char-count">{{ userDescription.length }} / 500</div>

        <div v-if="error" class="error-msg">{{ error }}</div>

        <div class="step-actions">
          <button type="button" class="btn btn-outline" @click="backToSelect">
            Back
          </button>
          <div class="step-actions-right">
            <button type="button" class="btn btn-outline" @click="onSkipToAdvanced">
              Skip, I'll write it
            </button>
            <button
              type="button"
              class="btn btn-primary"
              :disabled="generating || !userDescription.trim()"
              @click="onGenerate"
            >
              <Sparkles v-if="!generating" :size="16" />
              <span v-if="generating" class="spinner" />
              {{ generating ? 'Generating...' : 'Generate with AI' }}
            </button>
          </div>
        </div>
      </div>

      <!-- Step 2: fine-tune -->
      <div v-if="step === 2" class="step-content">
        <h3 class="step-title">{{ useAdvanced ? 'Write her persona' : 'Fine-tune her persona' }}</h3>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Name *</label>
            <input v-model="name" type="text" class="form-input" placeholder="e.g. Mia" maxlength="20" />
          </div>
          <div class="form-group">
            <label class="form-label">Short bio</label>
            <input v-model="description" type="text" class="form-input" placeholder="One line about her" maxlength="50" />
          </div>
        </div>

        <!-- Avatar upload -->
        <div class="form-group">
          <label class="form-label">Avatar</label>
          <div class="avatar-upload">
            <input ref="avatarInput" type="file" accept="image/*" class="file-input-hidden" @change="onAvatarChange" />
            <button type="button" class="avatar-pick" @click="triggerAvatar">
              <template v-if="avatarPreview">
                <img :src="avatarPreview" class="avatar-preview-img" />
              </template>
              <template v-else>
                <Camera :size="20" />
                <span>Pick a photo</span>
              </template>
            </button>
          </div>
        </div>

        <template v-if="useAdvanced">
          <div class="form-group">
            <label class="form-label">Persona (system prompt)</label>
            <textarea v-model="systemPrompt" class="form-textarea" rows="8" placeholder="Describe her personality, speaking style, backstory..." maxlength="5000" />
          </div>
        </template>

        <template v-else>
          <div class="form-group">
            <label class="form-label">Appearance</label>
            <textarea v-model="profile.appearance" class="form-textarea" rows="2" placeholder="What does she look like..." />
          </div>
          <div class="form-group">
            <label class="form-label">Backstory</label>
            <textarea v-model="profile.background" class="form-textarea" rows="3" placeholder="Her past, and how you two met..." />
          </div>
          <div class="form-group">
            <label class="form-label">Personality</label>
            <textarea v-model="profile.personality" class="form-textarea" rows="3" placeholder="The different sides of her..." />
          </div>
          <div class="form-group">
            <label class="form-label">Speaking style</label>
            <textarea v-model="profile.speaking_style" class="form-textarea" rows="2" placeholder="Tone, favourite words..." />
          </div>
          <div class="form-group">
            <label class="form-label">Signature phrases</label>
            <div class="expr-grid">
              <div class="expr-item">
                <span class="expr-label">Agreeing</span>
                <input
                  :value="(expr.confirm || []).join(', ')"
                  @input="profile.expression_style = { ...expr, confirm: ($event.target as HTMLInputElement).value.split(',').map(v => v.trim()).filter(Boolean) }"
                  class="form-input" placeholder="Okay!, Mm-hm"
                />
              </div>
              <div class="expr-item">
                <span class="expr-label">Apologising</span>
                <input
                  :value="(expr.apologize || []).join(', ')"
                  @input="profile.expression_style = { ...expr, apologize: ($event.target as HTMLInputElement).value.split(',').map(v => v.trim()).filter(Boolean) }"
                  class="form-input" placeholder="I'm sorry"
                />
              </div>
              <div class="expr-item">
                <span class="expr-label">Thanking</span>
                <input
                  :value="(expr.thanks || []).join(', ')"
                  @input="profile.expression_style = { ...expr, thanks: ($event.target as HTMLInputElement).value.split(',').map(v => v.trim()).filter(Boolean) }"
                  class="form-input" placeholder="Thank you!"
                />
              </div>
              <div class="expr-item">
                <span class="expr-label">Nicknames</span>
                <input
                  :value="(expr.pet_names || []).join(', ')"
                  @input="profile.expression_style = { ...expr, pet_names: ($event.target as HTMLInputElement).value.split(',').map(v => v.trim()).filter(Boolean) }"
                  class="form-input" placeholder="babe, sweetheart"
                />
              </div>
              <div class="expr-item">
                <span class="expr-label">Usual emoji</span>
                <input
                  :value="(expr.emoji || []).join('')"
                  @input="profile.expression_style = { ...expr, emoji: Array.from(($event.target as HTMLInputElement).value).filter(c => /\p{Emoji}/u.test(c)) }"
                  class="form-input" placeholder="🥰💕😊"
                />
              </div>
            </div>
          </div>
          <div class="form-group">
            <label class="form-label">Interests</label>
            <textarea v-model="profile.preferences" class="form-textarea" rows="2" placeholder="What she loves and hates..." />
          </div>
          <div class="form-group">
            <label class="form-label">Sample replies</label>
            <textarea v-model="profile.output_examples" class="form-textarea" rows="3" placeholder="Separate sample replies with \&#10;e.g. I miss you~🥰\\Long day today\\Good night✨" />
          </div>
          <div class="form-group">
            <label class="form-label">Rules</label>
            <textarea v-model="profile.behavioral_rules" class="form-textarea" rows="2" placeholder="Reply length, language, special constraints..." />
          </div>
        </template>

        <div v-if="error" class="error-msg">{{ error }}</div>

        <div class="step-actions">
          <button type="button" class="btn btn-outline" @click="step = 1">
            <ChevronLeft :size="16" /> Back
          </button>
          <button type="button" class="btn btn-primary" @click="doSubmitDescribe">
            Create character
          </button>
        </div>
      </div>
    </template>

    <!-- ═══════════════════════════════════════ -->
    <!-- Method two: chat log import               -->
    <!-- ═══════════════════════════════════════ -->
    <template v-if="mode === 'chat'">
      <!-- Step indicator -->
      <div class="steps">
        <div class="step-dot" :class="{ active: step >= 1, done: step > 1 }">1</div>
        <div class="step-line" :class="{ active: step > 1 }" />
        <div class="step-dot" :class="{ active: step >= 2 }">2</div>
      </div>

      <!-- Step 1: upload a chat log -->
      <div v-if="step === 1" class="step-content">
        <h3 class="step-title">Import a chat log</h3>
        <p class="step-desc">Paste a chat log and AI will distil the speaker's full persona — personality, speaking style, catchphrases, emotional patterns and all.</p>

        <!-- File upload -->
        <div class="form-group">
          <label class="form-label">Upload a file (optional)</label>
          <p class="field-hint">Supports .txt files, such as chat logs exported from WeChat or QQ</p>
          <input
            ref="chatFileInput"
            type="file"
            accept=".txt,.md,.json,.csv"
            class="file-input-hidden"
            @change="onChatFileSelected"
          />
          <button type="button" class="upload-btn" @click="triggerChatFile">
            {{ chatFileName || 'Choose a file...' }}
          </button>
        </div>

        <!-- Paste text -->
        <div class="form-group">
          <label class="form-label">Or paste the chat log</label>
          <textarea
            v-model="chatLogText"
            class="form-textarea chat-log-textarea"
            rows="8"
            placeholder="Paste the chat log here...&#10;&#10;Sample format (AI distils the persona of &quot;them&quot;):&#10;2024-03-15 14:30 Them (F): where should we eat today&#10;2024-03-15 14:31 Me: I'm craving hotpot~&#10;2024-03-15 14:32 Them (F): deal, usual spot"
          />
          <div class="char-count">{{ chatLogText.length }} chars</div>
        </div>

        <div v-if="error" class="error-msg">{{ error }}</div>

        <div class="step-actions">
          <button type="button" class="btn btn-outline" @click="backToSelect">
            Back
          </button>
          <button
            type="button"
            class="btn btn-primary"
            :disabled="analyzing || !chatLogText.trim()"
            @click="onAnalyzeChat"
          >
            <Brain v-if="!analyzing" :size="16" />
            <span v-if="analyzing" class="spinner" />
            {{ analyzing ? 'Distilling persona...' : 'Distil with AI' }}
          </button>
        </div>
      </div>

      <!-- Step 2: review and create -->
      <div v-if="step === 2" class="step-content">
        <h3 class="step-title">Fine-tune her persona</h3>
        <p class="step-desc">AI has distilled a persona from the chat log. Tweak any field below, then create her when you're happy with it.</p>

        <div class="form-row">
          <div class="form-group">
            <label class="form-label">Name *</label>
            <input v-model="name" type="text" class="form-input" placeholder="e.g. Mia" maxlength="20" />
          </div>
          <div class="form-group">
            <label class="form-label">Short bio</label>
            <input v-model="description" type="text" class="form-input" placeholder="One line about her" maxlength="50" />
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Avatar</label>
          <div class="avatar-upload">
            <input ref="avatarInput" type="file" accept="image/*" class="file-input-hidden" @change="onAvatarChange" />
            <button type="button" class="avatar-pick" @click="triggerAvatar">
              <template v-if="avatarPreview">
                <img :src="avatarPreview" class="avatar-preview-img" />
              </template>
              <template v-else>
                <Camera :size="20" />
                <span>Pick a photo</span>
              </template>
            </button>
          </div>
        </div>

        <div class="form-group">
          <label class="form-label">Appearance</label>
          <textarea v-model="profile.appearance" class="form-textarea" rows="2" placeholder="What does she look like..." />
        </div>
        <div class="form-group">
          <label class="form-label">Backstory</label>
          <textarea v-model="profile.background" class="form-textarea" rows="3" placeholder="Her past, and how you two met..." />
        </div>
        <div class="form-group">
          <label class="form-label">Personality</label>
          <textarea v-model="profile.personality" class="form-textarea" rows="3" placeholder="The different sides of her..." />
        </div>
        <div class="form-group">
          <label class="form-label">Speaking style</label>
          <textarea v-model="profile.speaking_style" class="form-textarea" rows="2" placeholder="Tone, favourite words..." />
        </div>
        <div class="form-group">
          <label class="form-label">Signature phrases</label>
          <div class="expr-grid">
            <div class="expr-item">
              <span class="expr-label">Agreeing</span>
              <input
                :value="(expr.confirm || []).join(', ')"
                @input="profile.expression_style = { ...expr, confirm: ($event.target as HTMLInputElement).value.split(',').map(v => v.trim()).filter(Boolean) }"
                class="form-input" placeholder="Okay!, Mm-hm"
              />
            </div>
            <div class="expr-item">
              <span class="expr-label">Apologising</span>
              <input
                :value="(expr.apologize || []).join(', ')"
                @input="profile.expression_style = { ...expr, apologize: ($event.target as HTMLInputElement).value.split(',').map(v => v.trim()).filter(Boolean) }"
                class="form-input" placeholder="I'm sorry"
              />
            </div>
            <div class="expr-item">
              <span class="expr-label">Thanking</span>
              <input
                :value="(expr.thanks || []).join(', ')"
                @input="profile.expression_style = { ...expr, thanks: ($event.target as HTMLInputElement).value.split(',').map(v => v.trim()).filter(Boolean) }"
                class="form-input" placeholder="Thank you!"
              />
            </div>
            <div class="expr-item">
              <span class="expr-label">Nicknames</span>
              <input
                :value="(expr.pet_names || []).join(', ')"
                @input="profile.expression_style = { ...expr, pet_names: ($event.target as HTMLInputElement).value.split(',').map(v => v.trim()).filter(Boolean) }"
                class="form-input" placeholder="babe, sweetheart"
              />
            </div>
            <div class="expr-item">
              <span class="expr-label">Usual emoji</span>
              <input
                :value="(expr.emoji || []).join('')"
                @input="profile.expression_style = { ...expr, emoji: Array.from(($event.target as HTMLInputElement).value).filter(c => /\p{Emoji}/u.test(c)) }"
                class="form-input" placeholder="🥰💕😊"
              />
            </div>
          </div>
        </div>
        <div class="form-group">
          <label class="form-label">Interests</label>
          <textarea v-model="profile.preferences" class="form-textarea" rows="2" placeholder="What she loves and hates..." />
        </div>
        <div class="form-group">
          <label class="form-label">Sample replies</label>
          <textarea v-model="profile.output_examples" class="form-textarea" rows="3" placeholder="Separate sample replies with \" />
        </div>
        <div class="form-group">
          <label class="form-label">Rules</label>
          <textarea v-model="profile.behavioral_rules" class="form-textarea" rows="2" placeholder="Reply length, language, special constraints..." />
        </div>

        <div v-if="error" class="error-msg">{{ error }}</div>

        <div class="step-actions">
          <button type="button" class="btn btn-outline" @click="step = 1">
            <ChevronLeft :size="16" /> Back
          </button>
          <button type="button" class="btn btn-primary" @click="doSubmitChat">
            Create character
          </button>
        </div>
      </div>
    </template>
  </form>

  <!-- API key warning dialog -->
  <div v-if="auth.showApiKeyWarning" class="api-key-overlay" @click.self="auth.dismissApiKeyWarning()">
    <div class="api-key-dialog">
      <div class="dialog-icon">🔑</div>
      <h3>No API key yet</h3>
      <p>Add your own API key to use AI chat, character generation and everything else.</p>
      <div class="dialog-actions">
        <button class="dialog-btn cancel" @click="auth.dismissApiKeyWarning()">Maybe later</button>
        <button class="dialog-btn confirm" @click="auth.dismissApiKeyWarning()">Got it</button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.wizard {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

/* ── Mode select ── */
.mode-select {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.mode-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.mode-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
  padding: 22px 16px;
  background: var(--color-surface);
  border: 2px solid var(--color-border);
  border-radius: var(--radius);
  cursor: pointer;
  transition: all var(--duration) var(--ease-bounce);
  text-align: center;
}
.mode-card:hover {
  border-color: var(--color-primary);
  background: var(--color-sakura-light);
  transform: translateY(-2px);
  box-shadow: var(--shadow-sm);
}
.mode-icon {
  width: 52px; height: 52px;
  border-radius: var(--radius-full);
  background: var(--color-sakura);
  display: flex; align-items: center; justify-content: center;
  color: var(--color-primary);
  transition: all var(--duration-fast);
}
.mode-card:hover .mode-icon {
  background: var(--color-primary);
  color: #fff;
}
.mode-name {
  font-family: var(--font-heading);
  font-size: var(--text-base);
  font-weight: 700;
  color: var(--color-text);
}
.mode-desc {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  line-height: 1.5;
}

/* ── Steps indicator ── */
.steps {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0;
  margin-bottom: 4px;
}
.step-dot {
  width: 28px; height: 28px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 12px; font-weight: 700;
  font-family: var(--font-heading);
  background: var(--color-bg);
  color: var(--color-text-muted);
  border: 2px solid var(--color-border);
  transition: all var(--duration) var(--ease-bounce);
}
.step-dot.active {
  background: var(--color-primary);
  color: #fff;
  border-color: var(--color-primary);
}
.step-dot.done {
  background: var(--color-success);
  border-color: var(--color-success);
}
.step-line {
  width: 50px; height: 2px;
  background: var(--color-border);
  transition: background var(--duration);
}
.step-line.active {
  background: var(--color-primary);
}

/* ── Step content ── */
.step-content {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.step-title {
  font-family: var(--font-heading);
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--color-text);
}
.step-desc {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  line-height: 1.5;
}

/* ── Form elements ── */
.form-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
.form-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
}
.form-label {
  font-size: var(--text-xs);
  font-weight: 600;
  color: var(--color-text-secondary);
  font-family: var(--font-heading);
}
.form-input {
  width: 100%;
  padding: 9px 12px;
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  outline: none;
  transition: all var(--duration-fast) var(--ease-smooth);
  background: var(--color-bg);
  color: var(--color-text);
  box-sizing: border-box;
}
.form-input:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(255,125,175,0.08);
}
.form-textarea {
  width: 100%;
  padding: 9px 12px;
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  outline: none;
  transition: all var(--duration-fast) var(--ease-smooth);
  background: var(--color-bg);
  color: var(--color-text);
  resize: vertical;
  min-height: 60px;
  line-height: 1.6;
  box-sizing: border-box;
}
.form-textarea:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(255,125,175,0.08);
}

.desc-textarea {
  width: 100%;
  padding: 12px 14px;
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  outline: none;
  transition: all var(--duration-fast) var(--ease-smooth);
  background: var(--color-bg);
  color: var(--color-text);
  resize: vertical;
  min-height: 100px;
  line-height: 1.7;
}
.desc-textarea:focus {
  border-color: var(--color-primary);
  box-shadow: 0 0 0 3px rgba(255,125,175,0.08);
}

.char-count {
  text-align: right;
  font-size: 11px;
  color: var(--color-text-muted);
  margin-top: 2px;
}

/* ── Expression style grid ── */
.expr-grid {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.expr-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.expr-label {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
  min-width: 60px;
}

/* ── Actions ── */
.step-actions {
  display: flex;
  justify-content: space-between;
  gap: 8px;
  margin-top: 4px;
}
.step-actions-right {
  display: flex;
  gap: 8px;
}

.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 9px 20px;
  border: none;
  border-radius: var(--radius-full);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-bounce);
  white-space: nowrap;
  flex-shrink: 0;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--color-primary);
  color: #fff;
}
.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-dark);
  transform: translateY(-1px);
  box-shadow: var(--shadow-sm);
}
.btn-outline {
  background: transparent;
  color: var(--color-text-secondary);
  border: 1.5px solid var(--color-border);
}
.btn-outline:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-sakura-light);
}

.spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(255,255,255,0.3);
  border-top-color: #fff;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

.error-msg {
  padding: 8px 12px;
  background: rgba(232,128,138,0.1);
  border: 1px solid rgba(232,128,138,0.2);
  border-radius: var(--radius-xs);
  font-size: var(--text-xs);
  color: var(--color-error);
  text-align: center;
}

/* ── Avatar upload ── */
.avatar-upload {
  display: flex;
  align-items: center;
  gap: 12px;
}
.avatar-pick {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  background: var(--color-sakura-light);
  border: 1.5px dashed var(--color-border-strong);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
  min-width: 100px;
  min-height: 60px;
  justify-content: center;
}
.avatar-pick:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-sakura);
}
.avatar-preview-img {
  width: 56px;
  height: 56px;
  border-radius: var(--radius-full);
  object-fit: cover;
  border: 2px solid var(--color-primary);
}

/* ── File upload ── */
.file-input-hidden { display: none; }

.field-hint {
  font-size: 10px;
  color: var(--color-text-muted);
  margin-top: -2px;
}

.upload-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  background: var(--color-sakura-light);
  border: 1.5px dashed var(--color-border-strong);
  border-radius: var(--radius-sm);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
}
.upload-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-sakura);
}

.chat-log-textarea {
  font-size: var(--text-xs);
  font-family: inherit;
  line-height: 1.8;
}

/* ── Analysis result ── */
.analysis-result {
  background: var(--color-sakura-light);
  border: 1px solid var(--color-primary-light);
  border-radius: var(--radius-sm);
  padding: 14px 16px;
}
.analysis-title {
  font-family: var(--font-heading);
  font-size: var(--text-sm);
  font-weight: 600;
  color: var(--color-primary-dark);
  margin-bottom: 10px;
}
.analysis-section {
  margin-bottom: 10px;
}
.analysis-section:last-child { margin-bottom: 0; }
.analysis-label {
  color: var(--color-primary-dark);
  font-weight: 600;
  font-size: var(--text-xs);
  margin-bottom: 2px;
}
.analysis-val {
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  line-height: 1.6;
  margin: 0;
}
.examples-val {
  font-style: italic;
  color: var(--color-primary-dark);
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

@media (max-width: 768px) {
  .form-row {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 480px) {
  .mode-card {
    padding: 16px 12px;
  }
  .mode-icon {
    width: 44px; height: 44px;
  }
  .mode-name {
    font-size: var(--text-sm);
  }
  .mode-desc {
    font-size: 11px;
  }
  .step-content {
    gap: 10px;
  }
  .step-actions {
    flex-direction: column;
    gap: 10px;
  }
  .step-actions-right {
    display: flex;
    gap: 8px;
  }
  .step-actions-right .btn {
    flex: 1;
    justify-content: center;
    padding: 9px 12px;
    font-size: 13px;
  }
  .step-actions > .btn {
    width: 100%;
    justify-content: center;
  }
  .desc-textarea {
    min-height: 80px;
    font-size: 14px;
    padding: 10px 12px;
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
  z-index: 2000;
  animation: apiFadeIn 0.2s ease;
}
.api-key-dialog {
  background: var(--color-bg);
  border-radius: var(--radius-md);
  padding: 32px 28px 24px;
  max-width: 360px;
  width: 90%;
  text-align: center;
  box-shadow: var(--shadow-lg);
  animation: apiScaleIn 0.25s var(--ease-bounce);
}
.dialog-icon { font-size: 40px; margin-bottom: 12px; }
.api-key-dialog h3 {
  font-size: 18px;
  font-weight: 700;
  font-family: var(--font-heading);
  color: var(--color-text);
  margin: 0 0 8px;
}
.api-key-dialog p {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
  margin: 0 0 20px;
  line-height: 1.6;
}
.dialog-actions {
  display: flex;
  gap: 10px;
  justify-content: center;
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
  background: var(--color-primary);
  color: #fff;
}
.dialog-btn.confirm:hover { opacity: 0.9; }

@keyframes apiFadeIn { from { opacity: 0; } to { opacity: 1; } }
@keyframes apiScaleIn { from { opacity: 0; transform: scale(0.92); } to { opacity: 1; transform: scale(1); } }
</style>
