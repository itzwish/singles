<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { storeToRefs } from 'pinia'
import { Camera, Edit3, Check, X, ChevronRight, Brain, Star, Trash2, LogOut, RefreshCw, Key, Eye, EyeOff, Lock, ShieldCheck } from 'lucide-vue-next'
import { UserProfile } from '@clerk/vue'
import TopBar from '@/components/layout/TopBar.vue'
import { useAuthStore } from '@/stores/auth'
import { useChatStore } from '@/stores/chat'
import { clerkUser } from '@/utils/clerk'
import api, { uploadApi } from '@/utils/http'

const router = useRouter()
const auth = useAuthStore()
const chat = useChatStore()
const { guestName, userAvatar, clerkSignedIn } = storeToRefs(auth)
const { characters, memories, consolidating } = storeToRefs(chat)

const editingName = ref(false)
const nameInput = ref('')
const savingName = ref(false)
const nameError = ref<string | null>(null)
const avatarInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const showMemories = ref(false)
const selectedCharId = ref<string | null>(null)
const loadingMemories = ref(false)
const editingMemId = ref<string | null>(null)
const editingMemContent = ref('')
const deletingMemId = ref<string | null>(null)

// API key
// Change password (legacy accounts only — Clerk manages its own credentials)
const showPwd = ref(false)
const pwdCurrent = ref('')
const pwdNew = ref('')
const pwdSaving = ref(false)
const pwdMsg = ref<string | null>(null)
const pwdOk = ref(false)

// Clerk account management modal
const showClerkProfile = ref(false)
const clerkProfileKey = ref(0)

function openClerkProfile() {
  clerkProfileKey.value++
  showClerkProfile.value = true
}

function togglePwd() {
  showPwd.value = !showPwd.value
  if (!showPwd.value) {
    pwdCurrent.value = ''
    pwdNew.value = ''
    pwdMsg.value = null
  }
}

async function changePwd() {
  if (!pwdCurrent.value || !pwdNew.value) return
  if (pwdNew.value.length < 6) {
    pwdMsg.value = 'Use at least 6 characters'
    pwdOk.value = false
    return
  }
  pwdSaving.value = true
  pwdMsg.value = null
  try {
    await api.post('/users/me/change-password', {
      current_password: pwdCurrent.value,
      new_password: pwdNew.value,
    })
    pwdOk.value = true
    pwdMsg.value = 'Password updated'
    pwdCurrent.value = ''
    pwdNew.value = ''
  } catch (e: any) {
    pwdOk.value = false
    pwdMsg.value = e.response?.data?.detail || 'Could not update your password'
  } finally {
    pwdSaving.value = false
  }
}

onMounted(async () => {
  await auth.loadUserInfo()
  await chat.loadCharacters()
})

function goBack() {
  // A profile opened from inside the app should return to the previous screen.
  // When it was opened directly (or the browser history has no in-app entry),
  // router.back() can leave the SPA entirely. Keep a stable Home fallback.
  const previousPath = window.history.state?.back
  if (typeof previousPath === 'string' && previousPath !== router.currentRoute.value.fullPath) {
    router.back()
    return
  }
  router.replace({ name: 'home' })
}

function triggerAvatar() {
  avatarInput.value?.click()
}

async function uploadAvatar(e: Event) {
  const target = e.target as HTMLInputElement
  const file = target.files?.[0]
  if (!file) return
  uploading.value = true
  try {
    const form = new FormData()
    form.append('file', file)
    const res = await uploadApi.post<{ avatar_url: string | null }>('/users/me/avatar', form)
    userAvatar.value = res.data.avatar_url
    auth.userAvatarVersion++
  } catch {
    // silently fail
  } finally {
    uploading.value = false
    target.value = ''
  }
}

function startEditName() {
  nameInput.value = guestName.value
  nameError.value = null
  editingName.value = true
}

async function saveName() {
  const username = nameInput.value.trim()
  nameError.value = null

  if (!username) {
    nameError.value = 'Username cannot be empty'
    return
  }
  if (username === guestName.value) {
    editingName.value = false
    return
  }

  savingName.value = true
  try {
    await auth.updateProfile({ username })
    editingName.value = false
  } catch (e: any) {
    nameError.value = e.response?.data?.detail || 'Could not update your username'
  } finally {
    savingName.value = false
  }
}

function cancelEditName() {
  editingName.value = false
  nameError.value = null
}

async function toggleMemories() {
  showMemories.value = !showMemories.value
  if (showMemories.value && !selectedCharId.value && characters.value.length > 0) {
    selectedCharId.value = characters.value[0].id
    await loadMemForChar(characters.value[0].id)
  }
}

async function onSelectChar(charId: string) {
  selectedCharId.value = charId
  await loadMemForChar(charId)
}

async function loadMemForChar(charId: string) {
  loadingMemories.value = true
  await chat.loadMemories(charId)
  loadingMemories.value = false
}

function startEditMem(m: { id: string; content: string }) {
  editingMemId.value = m.id
  editingMemContent.value = m.content
}

async function saveEditMem(id: string) {
  if (!editingMemContent.value.trim()) return
  await chat.updateMemory(id, { content: editingMemContent.value.trim() })
  editingMemId.value = null
}

async function confirmDeleteMem(id: string) {
  await chat.deleteMemory(id)
  deletingMemId.value = null
}

async function setMemImportance(id: string, importance: number) {
  await chat.updateMemory(id, { importance })
}

async function doLogout() {
  await auth.logout()
  router.push('/sign-in')
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })
}


</script>

<template>
  <div class="profile-view">
    <!-- Same shell as the other screens -->
    <TopBar title="Profile" :show-back="true" @back="goBack" />

    <div class="profile-content">
      <!-- Personal info card -->
      <div class="card profile-card">
        <div class="avatar-section" @click="triggerAvatar" :class="{ uploading }">
          <img v-if="userAvatar" :src="auth.getUserAvatarUrl()" class="profile-avatar-img" alt="" />
          <span v-else class="profile-avatar-text">{{ guestName?.[0] || '?' }}</span>
          <div class="avatar-edit-overlay">
            <Camera :size="16" />
          </div>
        </div>
        <input
          ref="avatarInput"
          type="file"
          accept="image/jpeg,image/png,image/webp,image/gif"
          class="file-input-hidden"
          @change="uploadAvatar"
        />

        <div class="name-row">
          <template v-if="editingName">
            <input
              v-model="nameInput"
              class="name-input"
              maxlength="12"
              :disabled="savingName"
              aria-label="Username"
              @keyup.enter="saveName"
              @keyup.escape="cancelEditName"
            />
            <button class="icon-btn save" :disabled="savingName" aria-label="Save username" @click="saveName"><Check :size="16" /></button>
            <button class="icon-btn" :disabled="savingName" aria-label="Cancel username edit" @click="cancelEditName"><X :size="16" /></button>
          </template>
          <template v-else>
            <span class="profile-name">{{ guestName }}</span>
            <button class="edit-btn" aria-label="Edit username" @click="startEditName"><Edit3 :size="14" /></button>
          </template>
        </div>

        <p v-if="nameError" class="name-error" role="alert">{{ nameError }}</p>
        <p class="profile-hint">Tap the photo to change it, or the pencil to change your username</p>
      </div>



      <!-- Account & security -->
      <div v-if="clerkSignedIn" class="card password-card" @click="openClerkProfile">
        <div class="card-row">
          <div class="card-row-left">
            <ShieldCheck :size="18" />
            <span>Account &amp; security</span>
          </div>
          <ChevronRight :size="18" class="chevron" />
        </div>
        <p class="mem-entry-hint">
          {{ clerkUser()?.email || 'Manage your email, password and connected accounts' }}
        </p>
      </div>

      <!-- Change password (legacy accounts) -->
      <div v-else class="card password-card" @click="!showPwd && (showPwd = true)">
        <div class="card-row" @click="togglePwd">
          <div class="card-row-left">
            <Lock :size="18" />
            <span>Change password</span>
          </div>
          <ChevronRight :size="18" class="chevron" :class="{ open: showPwd }" />
        </div>
        <p class="mem-entry-hint">Update the password you sign in with</p>
        <div v-if="showPwd" class="pwd-panel" @click.stop>
          <div class="pwd-field">
            <input
              v-model="pwdCurrent"
              type="password"
              class="pwd-input"
              placeholder="Current password"
              @keyup.enter="changePwd"
            />
          </div>
          <div class="pwd-field">
            <input
              v-model="pwdNew"
              type="password"
              class="pwd-input"
              placeholder="New password (min 6 characters)"
              @keyup.enter="changePwd"
            />
          </div>
          <button class="pwd-btn" :disabled="pwdSaving" @click="changePwd">
            {{ pwdSaving ? 'Saving...' : 'Update password' }}
          </button>
          <div v-if="pwdMsg" class="pwd-msg" :class="{ ok: pwdOk, fail: !pwdOk }">
            {{ pwdMsg }}
          </div>
        </div>
      </div>

      <!-- Memory management -->
      <div class="card memory-entry-card" @click="toggleMemories">
        <div class="card-row">
          <div class="card-row-left">
            <Brain :size="18" />
            <span>Memories</span>
          </div>
          <ChevronRight :size="18" class="chevron" :class="{ open: showMemories }" />
        </div>
        <p class="mem-entry-hint">Review and edit what each character remembers</p>
      </div>

      <div v-if="showMemories" class="card memory-panel">
        <!-- Character picker -->
        <div class="char-select">
          <button
            v-for="char in characters"
            :key="char.id"
            class="char-chip"
            :class="{ active: selectedCharId === char.id }"
            @click.stop="onSelectChar(char.id)"
          >
            {{ char.name }}
          </button>
        </div>

        <!-- Memory actions -->
        <div class="mem-toolbar">
          <button
            class="consolidate-btn"
            :disabled="consolidating"
            @click.stop="selectedCharId && chat.consolidateMemories(selectedCharId)"
          >
            <RefreshCw :size="13" :class="{ spinning: consolidating }" />
            <span>{{ consolidating ? 'Merging...' : 'Merge memories' }}</span>
          </button>
        </div>

        <!-- Memory list -->
        <div v-if="loadingMemories" class="mem-empty">Loading...</div>
        <div v-else-if="memories.length === 0" class="mem-empty">No memories yet</div>
        <div v-else class="mem-list">
          <div v-for="m in memories" :key="m.id" class="mem-card">
            <div class="mem-stars">
              <button
                v-for="n in 5" :key="n"
                class="star-btn"
                :class="{ active: n <= m.importance }"
                @click.stop="setMemImportance(m.id, n)"
              >
                <Star :size="12" :fill="n <= m.importance ? 'currentColor' : 'none'" />
              </button>
            </div>
            <div class="mem-content" v-if="editingMemId !== m.id">{{ m.content }}</div>
            <textarea
              v-else v-model="editingMemContent"
              class="mem-edit-input" rows="2"
              @keyup.escape="editingMemId = null"
            />
            <div class="mem-actions">
              <span class="mem-date">{{ formatDate(m.created_at) }}</span>
              <template v-if="editingMemId === m.id">
                <button class="act-btn save" @click.stop="saveEditMem(m.id)"><Check :size="14" /></button>
                <button class="act-btn" @click.stop="editingMemId = null"><X :size="14" /></button>
              </template>
              <template v-else>
                <button class="act-btn" @click.stop="startEditMem(m)"><Edit3 :size="13" /></button>
                <button v-if="deletingMemId === m.id" class="act-btn danger confirm" @click.stop="confirmDeleteMem(m.id)">Sure?</button>
                <button v-else class="act-btn" @click.stop="deletingMemId = m.id"><Trash2 :size="13" /></button>
              </template>
            </div>
          </div>
        </div>
      </div>

      <!-- Log out -->
      <div class="card logout-card" @click="doLogout">
        <div class="card-row">
          <div class="card-row-left" style="color: var(--color-error-ink)">
            <LogOut :size="18" />
            <span>Log out</span>
          </div>
        </div>
      </div>
    </div>
  </div>

  <!-- Clerk account management (email, password, connected accounts) -->
  <UserProfile v-if="showClerkProfile" :key="clerkProfileKey" />
</template>

<style scoped>
.profile-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

/* ── Content: the home screen's column and gutter, in two settings columns ── */
.profile-content {
  flex: 1;
  overflow-y: auto;
  width: 100%;
  max-width: 1100px;
  margin: 0 auto;
  padding: 40px 32px 64px;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  align-content: start;
  gap: 16px;
}
/* Identity, the memory panel and anything full-width runs across both columns. */
.profile-card,
.memory-panel,
.logout-card {
  grid-column: 1 / -1;
}

@media (max-width: 900px) {
  .profile-content {
    grid-template-columns: minmax(0, 1fr);
    padding: 24px 16px 48px;
  }
}

/* ── Card ── */
.card {
  background: var(--color-surface);
  border-radius: var(--radius);
  padding: 20px;
  border: 1px solid var(--color-border);
}
.card-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}
.card-row-left {
  display: flex; align-items: center; gap: 10px;
  font-size: var(--text-sm); font-weight: 500; color: var(--color-text);
}

/* ── Profile Card ── */
.profile-card {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 12px;
  padding: 28px 20px;
}
.avatar-section {
  width: 72px; height: 72px;
  border-radius: var(--radius-sm);
  background: var(--color-sakura);
  display: flex; align-items: center; justify-content: center;
  position: relative; cursor: pointer; overflow: hidden;
  flex-shrink: 0;
}
.avatar-section.uploading { opacity: 0.6; pointer-events: none; }
.profile-avatar-img {
  width: 100%; height: 100%;
  border-radius: inherit; object-fit: cover;
}
.profile-avatar-text {
  font-size: 28px; font-weight: 600; color: var(--color-primary-dark); font-family: var(--font-heading);
}
.avatar-edit-overlay {
  position: absolute; inset: 0;
  background: rgba(0,0,0,0.4);
  display: flex; align-items: center; justify-content: center;
  opacity: 0; transition: opacity var(--duration-fast);
  border-radius: inherit; color: #fff;
}
.avatar-section:hover .avatar-edit-overlay { opacity: 1; }
.file-input-hidden { display: none; }

.name-row {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  padding-left: 28px; /* offset for the edit button so the name stays optically centred */
}
.profile-name {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text);
}
.edit-btn {
  width: 24px; height: 24px;
  border: none; border-radius: var(--radius-xs);
  display: flex; align-items: center; justify-content: center;
  background: transparent; color: var(--color-text-secondary); cursor: pointer;
  transition: all var(--duration-fast);
  flex-shrink: 0;
}
.edit-btn:hover { background: var(--color-sakura-light); color: var(--color-text); }
.name-input {
  padding: 5px 10px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-xs);
  font-size: var(--text-base);
  font-family: var(--font-body);
  color: var(--color-text);
  background: var(--color-bg);
  outline: none;
  width: 160px;
}
.profile-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
}
.icon-btn {
  width: 28px; height: 28px;
  border: none; border-radius: var(--radius-xs);
  display: flex; align-items: center; justify-content: center;
  background: transparent; color: var(--color-text-secondary); cursor: pointer;
  transition: all var(--duration-fast);
}
.icon-btn:hover { background: var(--color-sakura-light); color: var(--color-text); }
.icon-btn.save { color: var(--color-success); }
.icon-btn:disabled,
.edit-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.name-error {
  margin: 0;
  color: var(--color-error-ink);
  background: var(--color-error-tint);
  border-radius: var(--radius-xs);
  padding: 5px 9px;
  font-size: var(--text-xs);
  text-align: center;
}

/* ── Chevron ── */
.chevron {
  color: var(--color-text-secondary);
  transition: transform var(--duration) var(--ease-smooth);
}
.chevron.open { transform: rotate(90deg); }

/* ── Memory Entry ── */
.memory-entry-card {
  border: 1px solid var(--color-border);
  background: var(--color-sakura-light);
}
.mem-entry-hint {
  margin-top: 6px;
  font-size: 13px;
  color: var(--color-text-secondary);
  padding-left: 28px;
}

/* ── Memory Panel ── */
.memory-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
.char-select {
  display: flex; gap: 8px; flex-wrap: wrap;
}
.char-chip {
  padding: 6px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: all var(--duration-fast);
}
.char-chip.active,
.char-chip:hover {
  border-color: var(--color-primary);
  background: var(--color-sakura-light);
  color: var(--color-primary);
}

.mem-toolbar {
  display: flex; justify-content: flex-end;
}
.consolidate-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 7px 14px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  background: var(--color-sakura-light);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  font-weight: 600;
  cursor: pointer;
  transition: border-color 140ms var(--ease-smooth), color 140ms var(--ease-smooth);
}
.consolidate-btn:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-text);
}
.consolidate-btn:disabled {
  opacity: 0.6; cursor: not-allowed;
}
.spinning { animation: spin 1s linear infinite; }

@keyframes spin {
  to { transform: rotate(360deg); }
}

.mem-empty {
  text-align: center; padding: 16px;
  font-size: var(--text-sm); color: var(--color-text-secondary);
}

.mem-list {
  display: flex; flex-direction: column; gap: 8px;
}
.mem-card {
  background: var(--color-bg);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  padding: 10px 12px;
}
.mem-stars {
  display: flex; gap: 2px; margin-bottom: 4px;
}
.star-btn {
  display: flex; padding: 0; border: none; background: none;
  color: var(--color-border); cursor: pointer;
  transition: all var(--duration-fast) var(--ease-bounce);
}
.star-btn.active { color: var(--color-gold); }
.star-btn:hover { transform: scale(1.2); color: var(--color-gold); }

.mem-content {
  font-size: var(--text-sm); color: var(--color-text); line-height: 1.5;
}
.mem-edit-input {
  width: 100%; padding: 6px 8px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-xs);
  font-size: var(--text-sm); font-family: var(--font-body);
  line-height: 1.5; outline: none; resize: vertical;
  box-sizing: border-box; background: var(--color-bg); color: var(--color-text);
}
.mem-actions {
  display: flex; align-items: center; gap: 4px; margin-top: 6px;
}
.mem-date {
  font-size: 12px; color: var(--color-text-secondary); flex: 1;
}
.act-btn {
  display: flex; align-items: center; justify-content: center;
  width: 24px; height: 24px;
  border: none; border-radius: var(--radius-xs);
  background: transparent; color: var(--color-text-secondary); cursor: pointer;
}
.act-btn:hover { background: var(--color-sakura-light); color: var(--color-text); }
.act-btn.save { color: var(--color-success); }
.act-btn.danger { color: var(--color-error); }
.act-btn.confirm { font-size: 12px; width: auto; padding: 0 6px; font-family: var(--font-body); font-weight: 600; }

/* ── Password ── */
.password-card {
  border: 1px solid var(--color-border);
  background: var(--color-surface);
}
.pwd-panel {
  margin-top: 12px;
  padding: 14px;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.pwd-field {
  display: flex;
  flex-direction: column;
}
.pwd-input {
  padding: 6px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  font-size: var(--text-sm);
  font-family: var(--font-body);
  color: var(--color-text);
  background: var(--color-bg);
  outline: none;
}
.pwd-input:focus { border-color: var(--color-primary); }
.pwd-btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-action);
  color: #fff;
  font-size: var(--text-sm);
  font-family: var(--font-body);
  font-weight: 600;
  cursor: pointer;
  align-self: flex-start;
}
.pwd-btn:hover:not(:disabled) { background: var(--color-action-hover); }
.pwd-btn:disabled { opacity: 0.6; cursor: not-allowed; }
.pwd-msg {
  font-size: var(--text-xs);
  padding: 4px 8px;
  border-radius: var(--radius-xs);
}
.pwd-msg.ok { color: var(--color-success-ink); background: var(--color-success-tint); }
.pwd-msg.fail { color: var(--color-error-ink); background: var(--color-error-tint); }

/* ── API Key ── */
.api-key-card {
  border: 1px solid var(--color-border);
  background: var(--color-sakura-light);
}
.api-badge {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: var(--radius-xs);
  font-family: var(--font-body);
  font-weight: 600;
  background: var(--color-success-tint);
  color: var(--color-success-ink);
}
.api-badge.empty {
  background: var(--color-warning-tint);
  color: var(--color-warning-ink);
}
.api-key-panel {
  margin-top: 12px;
  padding: 14px;
  background: var(--color-bg);
  border-radius: var(--radius-sm);
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.api-key-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.api-key-display {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: 1;
}
.api-key-masked,
.api-key-value {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}
.toggle-key-btn {
  display: flex;
  align-items: center;
  padding: 2px;
  border: none;
  background: none;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: var(--radius-xs);
}
.toggle-key-btn:hover { color: var(--color-text); }
.change-key-btn {
  padding: 4px 12px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: var(--text-xs);
  cursor: pointer;
  font-family: var(--font-body);
  transition: all var(--duration-fast);
  flex-shrink: 0;
}
.change-key-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.api-key-empty {
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: flex-start;
}
.api-key-empty p {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  margin: 0;
}
.set-key-btn {
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius-sm);
  background: var(--color-action);
  color: #fff;
  font-size: var(--text-sm);
  font-family: var(--font-body);
  font-weight: 600;
  cursor: pointer;
  transition: all var(--duration-fast);
}
.set-key-btn:hover { background: var(--color-action-hover); }
.api-key-edit {
  display: flex;
  align-items: center;
  gap: 8px;
}
.api-key-input {
  flex: 1;
  padding: 7px 10px;
  border: 1px solid var(--color-primary);
  border-radius: var(--radius-xs);
  font-size: var(--text-sm);
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-bg);
  outline: none;
}
.api-key-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
}
.api-key-hint {
  font-size: 13px;
  color: var(--color-text-secondary);
  margin: 0;
}

/* ── Config ── */
.config-divider {
  height: 1px;
  background: var(--color-border);
  margin: 4px 0;
}
.config-display {
  display: flex;
  align-items: center;
  gap: 12px;
}
.config-item {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex: 1;
}
.config-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-family: var(--font-body);
}
.config-value {
  font-size: var(--text-sm);
  color: var(--color-text);
  word-break: break-all;
}
.vendor-presets {
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.vendor-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.vendor-chip {
  padding: 5px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  font-size: 12px;
  font-family: var(--font-body);
  cursor: pointer;
  transition: all var(--duration-fast);
}
.vendor-chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}
.vendor-chip.active {
  background: var(--color-action);
  color: #fff;
  border-color: var(--color-action);
}
.config-edit {
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.config-field {
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.config-input {
  padding: 5px 8px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xs);
  font-size: var(--text-sm);
  font-family: inherit;
  color: var(--color-text);
  background: var(--color-bg);
  outline: none;
}
.config-input:focus {
  border-color: var(--color-primary);
}
.config-actions {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 4px;
}

.test-btn {
  padding: 5px 12px;
  border: 1px solid var(--color-success-ink);
  border-radius: var(--radius-xs);
  background: var(--color-success-tint);
  color: var(--color-success-ink);
  font-size: var(--text-xs);
  font-family: var(--font-body);
  cursor: pointer;
  transition: all var(--duration-fast);
  margin-left: auto;
}
.test-btn:hover:not(:disabled) {
  background: var(--color-success-ink);
  color: #fff;
}
.test-btn:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.test-result {
  font-size: var(--text-xs);
  padding: 4px 8px;
  border-radius: var(--radius-xs);
  margin-top: 4px;
}
.test-result.ok {
  color: var(--color-success-ink);
  background: var(--color-success-tint);
}
.test-result.fail {
  color: var(--color-error-ink);
  background: var(--color-error-tint);
}

/* ── Logout ── */
.logout-card .card-row { cursor: pointer; }

@media (max-width: 768px) {
  .profile-content {
    padding: 24px 16px 48px;
    gap: 12px;
  }
  .card {
    padding: 14px;
  }
  .profile-card {
    padding: 20px 14px;
  }
  .config-display {
    flex-wrap: wrap;
    gap: 8px;
  }
  .config-item {
    min-width: 45%;
  }
  .vendor-chips {
    gap: 4px;
  }
  .vendor-chip {
    font-size: 12px;
    padding: 4px 8px;
  }
  .config-actions {
    flex-wrap: wrap;
  }
  .mem-actions {
    flex-wrap: wrap;
  }
}

@media (max-width: 480px) {
  .profile-content {
    padding: 16px 12px 40px;
    gap: 10px;
  }
  .card {
    padding: 12px;
  }
  .profile-card {
    padding: 16px 12px;
  }
  .config-item {
    min-width: 100%;
  }
}
</style>
