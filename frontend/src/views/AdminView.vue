<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { ChevronLeft, ChevronRight } from 'lucide-vue-next'
import TopBar from '@/components/layout/TopBar.vue'
import api from '@/utils/http'
import type { SystemSettings } from '@/components/admin/AdminSettingsPanel.vue'

const router = useRouter()

// ── Types ──
interface UserItem {
  id: string
  email: string
  username: string
  membership_tier: 'free' | 'premium' | 'vip'
  is_active: boolean
  is_admin: boolean
  created_at: string
}

// ── Chat logs ──
interface ChatLogRow {
  id: string
  user_id: string
  username: string
  character_id: string | null
  character_name: string | null
  role: 'user' | 'assistant'
  content: string
  created_at: string
}

interface ChatLogsState {
  items: ChatLogRow[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  error: string
  search: string
}

// ── Dashboard stats ──
interface Stats {
  total_users: number
  vip_users: number
  total_characters: number
  total_conversations: number
  total_messages: number
  today_messages: number
  today_users: number
  active_users_today: number
}

// ── KPI finding ──
function findKpiFinding(stats: Stats): string {
  // The one fact that most needs attention
  if (stats.active_users_today > 0) {
    return `${stats.active_users_today} active users today`
  }
  if (stats.today_users > 0) {
    return `${stats.today_users} new signups today`
  }
  if (stats.total_messages > 0) {
    return `${stats.total_messages} total messages across ${stats.total_conversations} conversations`
  }
  return 'No data available'
}

// ── Dashboard ──
const stats = ref<Stats>({
  total_users: 0, vip_users: 0, total_characters: 0,
  total_conversations: 0, total_messages: 0,
  today_messages: 0, today_users: 0, active_users_today: 0,
})
const trend = ref<{ days: { date: string; label: string; count: number }[]; max: number }>({ days: [], max: 1 })
const kpiFinding = computed(() => findKpiFinding(stats.value))

async function loadStats() {
  try {
    const [sRes, tRes] = await Promise.all([
      api.get<Stats>('/admin/stats'),
      api.get<{ days: { date: string; label: string; count: number }[] }>('/admin/stats/trend'),
    ])
    stats.value = sRes.data
    trend.value = {
      days: tRes.data.days.map(d => ({ date: d.date, label: d.label, count: d.count })) as { date: string; label: string; count: number }[],
      max: Math.max(...tRes.data.days.map(d => d.count), 1)
    }
  } catch { /* ignore */ }
}

// ── User management ──
const users = ref<UserItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 15
const search = ref('')
const loading = ref(false)
const error = ref('')

async function loadUsers() {
  loading.value = true; error.value = ''
  try {
    const res = await api.get<{ items: UserItem[]; total: number }>('/admin/users', {
      params: { search: search.value, page: page.value, page_size: pageSize },
    })
    users.value = res.data.items
    total.value = res.data.total
  } catch (e: any) {
    error.value = e?.response?.data?.detail || 'Failed to load'
  } finally { loading.value = false }
}

function onSearch(q: string) { page.value = 1; search.value = q; loadUsers() }
function onPageChange(p: number) { page.value = p; loadUsers() }

async function onToggleActive(user: UserItem) {
  try {
    await api.patch(`/admin/users/${user.id}`, { is_active: !user.is_active })
    user.is_active = !user.is_active
  } catch { /* ignore */ }
}

async function onSetTier(user: UserItem, tier: string) {
  try {
    await api.patch(`/admin/users/${user.id}`, { membership_tier: tier })
    user.membership_tier = tier as UserItem['membership_tier']
  } catch { /* ignore */ }
}

const resettingUserId = ref<string | null>(null)
const tempPassword = ref('')
const tempPasswordUser = ref('')

async function onResetPassword(user: UserItem) {
  resettingUserId.value = user.id
  try {
    const res = await api.post<{ temp_password: string; username: string }>(`/admin/users/${user.id}/reset-password`)
    tempPassword.value = res.data.temp_password
    tempPasswordUser.value = res.data.username
  } catch { /* ignore */ }
  finally { resettingUserId.value = null }
}

function closePwdDialog() {
  tempPassword.value = ''
  tempPasswordUser.value = ''
}

// ── System API settings ──
const sysSettings = ref({
  ai_provider: 'gemini' as 'gemini' | 'ollama',
  ai_fallback_enabled: true,
  gemini_fallback_models: '',
  ollama_fallback_models: '',
  vision_enabled: true,
  vision_model: '',
  gemini_model: '',
  ollama_base_url: '',
  ollama_model: '',
  ollama_vision_model: '',
})
const settingsSaving = ref(false)
const settingsSaved = ref(false)

async function loadSettings() {
  try {
    const r = await api.get<SystemSettings>('/admin/settings')
    sysSettings.value = r.data
  } catch { /* ignore */ }
}

async function onSaveSettings(data: SystemSettings) {
  settingsSaving.value = true; settingsSaved.value = false
  try {
    const r = await api.put<SystemSettings>('/admin/settings', data)
    sysSettings.value = r.data
    settingsSaved.value = true
    setTimeout(() => { settingsSaved.value = false }, 2000)
  } catch { /* ignore */ }
  finally { settingsSaving.value = false }
}

const chatLogPage = ref(1)
const chatLogPageSize = 25
let chatLogSearchDebounce: ReturnType<typeof setTimeout> | null = null
function _clearChatLogSearchDebounce() {
  if (chatLogSearchDebounce !== null) {
    clearTimeout(chatLogSearchDebounce)
    chatLogSearchDebounce = null
  }
}
function _scheduleChatLogSearch() {
  _clearChatLogSearchDebounce()
  chatLogSearchDebounce = setTimeout(() => {
    chatLogSearchDebounce = null
    chatLogPage.value = 1
    loadChatLogs()
  }, 250)
}

const filterUserId = ref('')
const filterCharacterId = ref('')
const filterRole = ref('all')
const logsLoading = ref(false)
const logsTotal = ref(0)
const chatLogs = ref<ChatLogRow[]>([])

const filteredLogs = computed(() => {
  const items = chatLogs.value || []
  const text = (search.value || '').trim().toLowerCase()
  const userId = (filterUserId.value || '').trim()
  const characterId = (filterCharacterId.value || '').trim()
  const role = filterRole.value

  return items.filter((log: any) => {
    if (userId && String(log.user_id) !== userId) return false
    if (characterId && String(log.character_id) !== characterId) return false
    if (role !== 'all' && log.role !== role) return false
    if (text) {
      const haystack = [
        log.content || '',
        log.username || '',
        log.user_email || '',
        log.character_name || '',
      ].join(' ').toLowerCase()
      if (!haystack.includes(text)) return false
    }
    return true
  })
})

async function loadChatLogs(resetPage = true) {
  if (resetPage) chatLogPage.value = 1
  logsLoading.value = true
  try {
    const params: Record<string, any> = {
      page: chatLogPage.value,
      page_size: chatLogPageSize,
    }
    if (search.value.trim()) params.search = search.value.trim()
    if (filterUserId.value) params.user_id = filterUserId.value
    if (filterCharacterId.value) params.character_id = filterCharacterId.value
    if (filterRole.value !== 'all') params.role = filterRole.value

    const res = await api.get<{ items: ChatLogRow[]; total: number }>('/admin/chat-logs', {
      params,
    })
    chatLogs.value = res.data.items
    logsTotal.value = res.data.total
  } catch { /* ignore */ }
  finally { logsLoading.value = false }
}

function applyFilter() { chatLogPage.value = 1; loadChatLogs(false) }
function onSearchDebounce() { _scheduleChatLogSearch() }

function prevPage() {
  if (chatLogPage.value > 1) {
    chatLogPage.value--
    loadChatLogs(false)
  }
}
function nextPage() {
  const maxPage = Math.max(1, Math.ceil(logsTotal.value / chatLogPageSize))
  if (chatLogPage.value < maxPage) {
    chatLogPage.value++
    loadChatLogs(false)
  }
}

onMounted(() => { loadStats(); loadUsers(); loadChatLogs() })
</script>



<template>
  <div class="admin-view">
    <TopBar title="Admin" show-back @back="router.push('/')" />
    <div class="admin-content">
      <AdminStatsGrid
        :stats="stats"
        :trend="trend"
      />
      <AdminUserTable
        :users="users"
        :total="total"
        :page="page"
        :page-size="pageSize"
        :loading="loading"
        :error="error"
        @search="onSearch"
        @update:page="onPageChange"
        @toggle-active="onToggleActive"
        @set-tier="onSetTier"
      />

      <!-- Temporary password dialog -->
      <div v-if="tempPassword" class="pwd-dialog-overlay" @click.self="closePwdDialog">
        <div class="pwd-dialog">
          <h3>Password reset</h3>
          <p class="pwd-dialog-user">User: <strong>{{ tempPasswordUser }}</strong></p>
          <div class="temp-pwd-box">
            <code>{{ tempPassword }}</code>
          </div>
          <p class="pwd-dialog-note">Send this temporary password to the user — they must change it at first sign-in</p>
          <button class="btn-submit" @click="closePwdDialog">Done</button>
        </div>
      </div>

      <!-- Chat logs section -->
      <section class="chat-logs-section" v-if="users.length > 0">
        <h2 class="section-header">Chat Audit Logs</h2>
        <p class="section-subtitle">Browse any user's chat with any bot by username</p>
        <div class="logs-filters">
          <div class="filter-group">
            <label>Search:</label>
            <input
              v-model="search"
              type="text"
              placeholder="Search by username, character, or message content"
              @input="onSearchDebounce"
              @keyup.enter="applyFilter"
            />
            <button @click="applyFilter">Apply</button>
          </div>
          <div class="filter-group">
            <label>User:</label>
            <select v-model="filterUserId">
              <option value="">All users</option>
              <option v-for="u in users" :key="u.id" :value="u.id">{{ u.username }}</option>
            </select>
          </div>
          <div class="filter-group">
            <label>Character:</label>
            <select v-model="filterCharacterId">
              <option value="">All characters</option>
            </select>
          </div>
          <div class="filter-group">
            <label>Role:</label>
            <select v-model="filterRole">
              <option value="">All roles</option>
              <option value="user">User messages</option>
              <option value="assistant">Bot messages</option>
            </select>
          </div>
        </div>

        <div v-if="logsLoading" class="loading-msg">Loading...</div>

        <div v-else>
          <div v-if="filteredLogs.length === 0" class="empty-msg">
            No chat logs match the filters.
          </div>

          <div v-else>
            <table class="chat-logs-table">
              <thead>
                <tr>
                  <th>User</th>
                  <th>Character</th>
                  <th>Role</th>
                  <th>Message preview</th>
                  <th>Date</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="log in filteredLogs" :key="log.id">
                  <td class="log-user">{{ log.username }}</td>
                  <td class="log-character">{{ log.character_name || '-' }}</td>
                  <td>
                    <span
                      class="role-badge"
                      :class="{ user: 'role-user', assistant: 'role-assistant' }[log.role]"
                    >{{ log.role === 'user' ? 'User' : 'Bot' }}</span>
                  </td>
                  <td class="log-preview">
                    <div v-html="log.content" class="preview-content"></div>
                  </td>
                  <td class="log-date">{{ new Date(log.created_at).toLocaleDateString('en-US') }}</td>
                </tr>
              </tbody>
            </table>

            <div class="pagination" v-if="logsTotal > pageSize">
              <button :disabled="chatLogPage <= 1" @click="prevPage"><ChevronLeft :size="14" /></button>
              <span class="page-info">Page {{ chatLogPage }} / {{ Math.max(1, Math.ceil(logsTotal / chatLogPageSize)) }} ({{ logsTotal }} total)</span>
              <button :disabled="chatLogPage * chatLogPageSize >= logsTotal" @click="nextPage"><ChevronRight :size="14" /></button>
            </div>
          </div>
        </div>
      </section>
      <p v-else="users.length === 0" class="empty-msg">No users found. Add users first.</p>
    </div>
  </div>
</template>

<style scoped>
.admin-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--color-bg);
}

.admin-content {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px 32px;
  background: var(--color-surface);
}

.section-header {
  font-family: var(--font-heading);
  font-size: 20px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid var(--color-border-strong);
}

.section-subtitle {
  font-size: 13px;
  color: var(--color-text-muted);
  margin-bottom: 20px;
  max-width: 600px;
}

.logs-filters {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  padding: 20px 24px;
  margin-bottom: 24px;
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
  align-items: center;
}

.filter-group {
  display: flex;
  flex-direction: column;
  min-width: 150px;
  gap: 4px;
}

.filter-group label {
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.filter-group input,
.filter-group select {
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

.filter-group input:focus,
.filter-group select:focus { border-color: var(--color-primary); }

.apply-btn {
  padding: 8px 16px;
  border: none;
  border-radius: 8px;
  background: var(--color-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}
.apply-btn:hover:not(:disabled) { background: var(--color-primary-dark); }

.apply-btn:disabled { opacity: 0.5; cursor: not-allowed; }

.chat-logs-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
  margin-bottom: 24px;
}

.chat-logs-table th {
  text-align: left;
  padding: 12px 16px;
  background: var(--color-bg);
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text-muted);
  text-transform: uppercase;
  letter-spacing: 0.5px;
  white-space: nowrap;
}

.chat-logs-table td {
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
  color: var(--color-text);
  vertical-align: middle;
}

.chat-logs-table tbody tr { transition: background 0.15s; }
.chat-logs-table tbody tr:hover { background: var(--color-sakura-light); }

.log-user {
  font-weight: 600;
  color: var(--color-text);
}

.log-character {
  color: var(--color-text-muted);
  font-size: 13px;
}

.role-badge {
  display: inline-block;
  padding: 3px 8px;
  border-radius: 10px;
  font-size: 11px;
  font-weight: 600;
  color: var(--color-text);
}
.role-badge.user { background: var(--color-bg); color: var(--color-text-muted); }
.role-badge.assistant { background: var(--color-sakura-light); color: var(--color-primary-dark); }

.log-preview {
  max-width: 300px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--color-text-muted);
  font-size: 12px;
}

.log-date {
  white-space: nowrap;
  font-size: 12px;
  color: var(--color-text-muted);
}

.pagination {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  padding: 12px 16px;
  border-top: 1px solid var(--color-border);
}

.pagination button {
  width: 30px; height: 30px;
  border-radius: 8px;
  border: 1px solid var(--color-border);
  background: var(--color-surface);
  color: var(--color-text-secondary);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: all 0.15s;
}
.pagination button:hover:not(:disabled) {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-sakura-light);
}
.pagination button:disabled { opacity: 0.3; cursor: not-allowed; }
.page-info { font-size: 13px; color: var(--color-text-muted); }

.empty-msg {
  padding: 40px 20px;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 13px;
}

.loading-msg {
  padding: 40px 20px;
  text-align: center;
  color: var(--color-text-muted);
  font-size: 13px;
}

@media (max-width: 1200px) {
  .logs-filters { padding: 16px; }
}

@media (max-width: 768px) {
  .admin-content { padding: 16px; }
  .logs-filters { flex-direction: column; padding: 12px; gap: 8px; }
  .filter-group { min-width: 100%; }
  .chat-logs-table th, .chat-logs-table td { padding: 8px 12px; }
  .chat-logs-table th { font-size: 10px; }
  .chat-logs-table td { font-size: 12px; }
  .role-badge { padding: 2px 6px; font-size: 10px; }
  .log-preview { max-width: 150px; font-size: 11px; }
}
</style>

