<script setup lang="ts">
import { ref, reactive, watch } from 'vue'
import { Palette, Save, Cpu, Cloud } from 'lucide-vue-next'

export interface SystemSettings {
  ai_provider: 'gemini' | 'ollama'
  ai_fallback_enabled: boolean
  gemini_fallback_models: string
  ollama_fallback_models: string
  vision_enabled: boolean
  vision_model: string
  gemini_api_key: string
  gemini_model: string
  ollama_base_url: string
  ollama_api_key: string
  ollama_model: string
  ollama_vision_model: string
}

const props = defineProps<{
  settings: SystemSettings
  saving: boolean
  saved: boolean
}>()

const emit = defineEmits<{
  save: [data: SystemSettings]
}>()

const local = reactive<SystemSettings>({ ...props.settings })
watch(() => props.settings, (v) => Object.assign(local, v))

const showVisionKeys = ref(false)
const showOllamaKey = ref(false)

function emitToggle(key: 'vision_enabled' | 'ai_fallback_enabled') {
  local[key] = !local[key]
  emit('save', { ...local })
}

function selectProvider(provider: 'gemini' | 'ollama') {
  local.ai_provider = provider
  emit('save', { ...local })
}
</script>

<template>
  <div class="panel settings-panel">
    <div class="panel-header">
      <Palette :size="18" class="panel-icon" />
      <h3 class="panel-title">System API settings</h3>
      <button class="save-btn" :disabled="saving" @click="emit('save', { ...local })">
        <Save :size="14" />
        {{ saving ? 'Saving...' : 'Save settings' }}
      </button>
      <span v-if="saved" class="saved-tag">✓ Saved</span>
    </div>

    <div class="settings-grid">
      <div class="settings-card">
        <div class="settings-card-header">
          <Cloud :size="16" />
          <span>Default provider</span>
        </div>
        <div class="settings-body">
          <div class="provider-row">
            <button
              class="provider-btn"
              :class="{ active: local.ai_provider !== 'ollama' }"
              @click="selectProvider('gemini')"
            >
              Gemini
            </button>
            <button
              class="provider-btn"
              :class="{ active: local.ai_provider === 'ollama' }"
              @click="selectProvider('ollama')"
            >
              Ollama
            </button>
          </div>
          <p class="hint">
            Users who add their own API key in their profile keep using Gemini with that key.
          </p>
          <label class="inline-toggle">
            <input type="checkbox" :checked="local.ai_fallback_enabled" @change="emitToggle('ai_fallback_enabled')" />
            <span>Automatic fallback when a provider or model is unavailable</span>
          </label>
          <div class="field">
            <label>Gemini model</label>
            <input type="text" v-model="local.gemini_model" placeholder="gemini-3.5-flash" />
          </div>
          <div class="field">
            <label>Gemini fallback models (comma separated)</label>
            <input type="text" v-model="local.gemini_fallback_models" placeholder="gemini-3-flash, gemini-flash-latest" />
          </div>
          <div class="field">
            <label>Gemini API key</label>
            <div class="key-row">
              <input :type="showVisionKeys ? 'text' : 'password'" v-model="local.gemini_api_key" placeholder="Shared Gemini key" />
              <button class="eye-btn" @click="showVisionKeys = !showVisionKeys">
                <EyeOff v-if="showVisionKeys" :size="14" />
                <Eye v-else :size="14" />
              </button>
            </div>
          </div>
        </div>
      </div>

      <div class="settings-card">
        <div class="settings-card-header">
          <Cpu :size="16" />
          <span>Ollama</span>
        </div>
        <div class="settings-body">
          <div class="field">
            <label>Base URL</label>
            <input type="text" v-model="local.ollama_base_url" placeholder="https://ollama.com/v1" />
          </div>
          <div class="field">
            <label>API Key</label>
            <div class="key-row">
              <input :type="showOllamaKey ? 'text' : 'password'" v-model="local.ollama_api_key" placeholder="Ollama Cloud API key" />
              <button class="eye-btn" @click="showOllamaKey = !showOllamaKey">
                <EyeOff v-if="showOllamaKey" :size="14" />
                <Eye v-else :size="14" />
              </button>
            </div>
          </div>
          <div class="field">
            <label>Model</label>
            <input type="text" v-model="local.ollama_model" placeholder="gpt-oss:120b" />
          </div>
          <div class="field">
            <label>Fallback models (comma separated)</label>
            <input type="text" v-model="local.ollama_fallback_models" placeholder="gpt-oss:20b" />
          </div>
          <div class="field">
            <label>Vision model (optional)</label>
            <input type="text" v-model="local.ollama_vision_model" placeholder="qwen3-vl:32b" />
          </div>
        </div>
      </div>

      <div class="settings-card">
        <div class="settings-card-header">
          <Save :size="16" />
          <span>Vision API</span>
          <label class="toggle-switch">
            <input type="checkbox" :checked="local.vision_enabled" @change="emitToggle('vision_enabled')" />
            <span class="toggle-slider" />
          </label>
        </div>
        <div class="settings-body">
          <div class="field">
            <label>Gemini vision model</label>
            <input type="text" v-model="local.vision_model" placeholder="gemini-3.5-flash" />
          </div>
          <p class="hint">
            Images are described by the active provider's vision model; the Gemini vision
            model applies when Gemini is selected.
          </p>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.panel {
  background: var(--color-surface);
  border-radius: 16px;
  border: 1px solid var(--color-border);
  overflow: hidden;
  margin-bottom: 20px;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 16px 20px;
  border-bottom: 1px solid var(--color-border);
  flex-wrap: wrap;
}

.panel-icon { color: var(--color-primary); flex-shrink: 0; }

.panel-title {
  font-family: var(--font-heading);
  font-size: 15px;
  font-weight: 700;
  color: var(--color-text);
}

.save-btn {
  margin-left: auto;
  display: inline-flex; align-items: center; gap: 6px;
  padding: 7px 16px;
  border: none;
  border-radius: 8px;
  background: var(--color-primary);
  color: #fff;
  font-size: 13px; font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}
.save-btn:hover:not(:disabled) { background: var(--color-primary-dark); }
.save-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.saved-tag {
  font-size: 12px; font-weight: 600; color: var(--color-primary);
  padding: 4px 10px; background: var(--color-surface);
  border-radius: 6px;
}

.settings-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 0;
}

.settings-card {
  padding: 20px;
  border-right: 1px solid var(--color-border);
}
.settings-card:last-child { border-right: none; }

.settings-card-header {
  display: flex; align-items: center; gap: 8px;
  font-size: 14px; font-weight: 600;
  color: var(--color-text);
  margin-bottom: 16px;
}
.settings-card-header svg { color: var(--color-primary); flex-shrink: 0; }

.toggle-switch {
  margin-left: auto;
  position: relative; width: 40px; height: 22px;
  cursor: pointer;
}
.toggle-switch input { display: none; }
.toggle-slider {
  position: absolute; inset: 0;
  background: var(--color-border-strong);
  border-radius: 22px;
  transition: background 0.2s;
}
.toggle-slider::after {
  content: '';
  position: absolute; top: 2px; left: 2px;
  width: 18px; height: 18px;
  border-radius: 50%;
  background: #fff;
  transition: transform 0.2s;
}
.toggle-switch input:checked + .toggle-slider { background: var(--color-primary); }
.toggle-switch input:checked + .toggle-slider::after { transform: translateX(18px); }

.settings-body {
  display: flex; flex-direction: column; gap: 12px;
}

.field {
  display: flex; flex-direction: column; gap: 4px;
}
.field label {
  font-size: 11px; font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase; letter-spacing: 0.5px;
}
.field input, .field select {
  padding: 8px 12px;
  border: 1.5px solid var(--color-border);
  border-radius: 8px;
  font-size: 13px;
  background: var(--color-bg);
  color: var(--color-text);
  outline: none;
  transition: border-color 0.2s;
  font-family: var(--font-body);
}
.field input:focus, .field select:focus { border-color: var(--color-primary); }
.field select { cursor: pointer; }

.field-row { display: flex; gap: 12px; }

.provider-row { display: flex; gap: 8px; }
.provider-btn {
  flex: 1;
  padding: 8px 12px;
  border: 1.5px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
  color: var(--color-text-muted);
  font-size: 13px; font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.provider-btn:hover { border-color: var(--color-primary); }
.provider-btn.active {
  border-color: var(--color-primary);
  background: var(--color-sakura-light);
  color: var(--color-primary-dark);
}

.inline-toggle {
  display: flex; align-items: flex-start; gap: 8px;
  font-size: 12px; color: var(--color-text);
  cursor: pointer;
}
.inline-toggle input { margin-top: 2px; accent-color: var(--color-primary); }

.hint {
  font-size: 11.5px;
  line-height: 1.5;
  color: var(--color-text-muted);
  margin: 0;
}

.key-row { display: flex; gap: 0; }
.key-row input {
  flex: 1;
  border-top-right-radius: 0; border-bottom-right-radius: 0;
  border-right: none;
}
.eye-btn {
  width: 36px;
  border: 1.5px solid var(--color-border);
  border-left: none;
  border-radius: 0 8px 8px 0;
  background: var(--color-bg);
  color: var(--color-text-muted);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.eye-btn:hover { color: var(--color-primary); background: var(--color-sakura-light); }

@media (max-width: 768px) {
  .settings-grid { grid-template-columns: 1fr; }
  .settings-card { border-right: none; border-bottom: 1px solid var(--color-border); }
  .settings-card:last-child { border-bottom: none; }
}
</style>
