<script setup lang="ts">
import { ref, computed } from 'vue'
import { Search, ChevronLeft, ChevronRight, KeyRound } from 'lucide-vue-next'

export interface UserItem {
  id: string
  email: string
  username: string
  membership_tier: 'free' | 'premium' | 'vip'
  is_active: boolean
  is_admin: boolean
  created_at: string
}

const props = defineProps<{
  users: UserItem[]
  total: number
  page: number
  pageSize: number
  loading: boolean
  error: string
  resettingUserId: string | null
}>()

const emit = defineEmits<{
  search: [q: string]
  'update:page': [p: number]
  toggleActive: [user: UserItem]
  setTier: [user: UserItem, tier: string]
  resetPassword: [user: UserItem]
}>()

const searchInput = ref('')

const totalPages = computed(() => Math.ceil(props.total / props.pageSize) || 1)

function doSearch() { emit('search', searchInput.value) }
function prevPage() { if (props.page > 1) emit('update:page', props.page - 1) }
function nextPage() { if (props.page * props.pageSize < props.total) emit('update:page', props.page + 1) }
</script>

<template>
  <div class="user-panel">
    <div class="panel-header">
      <Search :size="18" class="panel-icon" />
      <h3 class="panel-title">Users</h3>
      <div class="search-box">
        <input
          v-model="searchInput"
          type="text"
          class="search-input"
          placeholder="Search email or username..."
          @keyup.enter="doSearch"
        />
        <button class="search-btn" @click="doSearch">Search</button>
      </div>
    </div>

    <p v-if="error" class="error-msg">{{ error }}</p>

    <div class="table-wrap" v-if="users.length">
      <table class="user-table">
        <thead>
          <tr>
            <th style="width:40px"></th>
            <th>User</th>
            <th>Plan</th>
            <th>Status</th>
            <th>Role</th>
            <th>Joined</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="u in users" :key="u.id" :class="{ inactive: !u.is_active }">
            <td>
              <div class="user-avatar-circle" :class="u.membership_tier">
                {{ u.username[0]?.toUpperCase() || '?' }}
              </div>
            </td>
            <td>
              <div class="user-cell">
                <span class="user-name">{{ u.username }}</span>
                <span class="user-email">{{ u.email }}</span>
              </div>
            </td>
            <td>
              <span class="tier-chip" :class="u.membership_tier">
                {{ u.membership_tier === 'vip' ? 'VIP' : u.membership_tier === 'premium' ? 'Premium' : 'Free' }}
              </span>
            </td>
            <td>
              <span class="status-chip" :class="{ active: u.is_active }">
                {{ u.is_active ? 'Active' : 'Disabled' }}
              </span>
            </td>
            <td>
              <span v-if="u.is_admin" class="role-chip admin">Admin</span>
              <span v-else class="role-chip user">User</span>
            </td>
            <td class="date-cell">{{ new Date(u.created_at).toLocaleDateString('en-US') }}</td>
            <td class="actions-cell" v-if="!u.is_admin">
              <button class="act-btn" :class="{ danger: u.is_active }" @click="emit('toggleActive', u)">
                {{ u.is_active ? 'Disable' : 'Enable' }}
              </button>
              <button class="act-btn" @click="emit('setTier', u, u.membership_tier === 'vip' ? 'free' : 'vip')">
                {{ u.membership_tier === 'vip' ? 'Downgrade' : 'Make VIP' }}
              </button>
              <button
                class="act-btn reset-btn"
                :disabled="resettingUserId === u.id"
                @click="emit('resetPassword', u)"
              >
                <KeyRound v-if="resettingUserId !== u.id" :size="13" />
                <span v-else class="spinner-sm" />
                {{ resettingUserId === u.id ? 'Resetting' : 'Reset password' }}
              </button>
            </td>
            <td v-else class="actions-cell">
              <span class="self-tag">—</span>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <p v-if="!loading && !users.length && !error" class="empty-msg">No users yet</p>
    <p v-if="loading" class="loading-msg">Loading...</p>

    <div class="pagination" v-if="total > pageSize">
      <button :disabled="page <= 1" @click="prevPage"><ChevronLeft :size="14" /></button>
      <span class="page-info">Page {{ page }} / {{ totalPages }} ({{ total }} total)</span>
      <button :disabled="page * pageSize >= total" @click="nextPage"><ChevronRight :size="14" /></button>
    </div>
  </div>
</template>

<style scoped>
.user-panel {
  background: var(--color-surface);
  border-radius: 16px;
  border: 1px solid var(--color-border);
  overflow: hidden;
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

.search-box {
  display: flex; align-items: center; gap: 8px;
  margin-left: auto;
}

.search-input {
  width: 200px;
  padding: 7px 12px;
  border: 1.5px solid var(--color-border);
  border-radius: 8px;
  font-size: 13px;
  background: var(--color-bg);
  color: var(--color-text);
  outline: none;
  transition: border-color 0.2s;
}
.search-input:focus { border-color: var(--color-primary); }

.search-btn {
  padding: 7px 14px;
  border: none;
  border-radius: 8px;
  background: var(--color-primary);
  color: #fff;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s;
}
.search-btn:hover { background: var(--color-primary-dark); }

.table-wrap { overflow-x: auto; }

.user-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.user-table th {
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

.user-table td {
  padding: 10px 16px;
  border-top: 1px solid var(--color-border);
  color: var(--color-text);
  vertical-align: middle;
}

.user-table tbody tr { transition: background 0.15s; }
.user-table tbody tr:hover { background: var(--color-sakura-light); }
.user-table tbody tr.inactive { opacity: 0.45; }
.user-table tbody tr.inactive:hover { opacity: 0.65; }

.user-avatar-circle {
  width: 34px; height: 34px;
  border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-size: 13px; font-weight: 700;
  color: var(--color-text-secondary);
  background: var(--color-bg);
  border: 2px solid var(--color-border);
}
.user-avatar-circle.vip {
  background: var(--color-bg);
  border-color: var(--color-border);
  color: var(--color-text-muted);
}

.user-cell { display: flex; flex-direction: column; gap: 2px; }
.user-name { font-weight: 600; }
.user-email { font-size: 11px; color: var(--color-text-muted); }

.tier-chip {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 10px;
  font-size: 11px; font-weight: 600;
  background: var(--color-bg);
  color: var(--color-text-muted);
}
.tier-chip.vip { background: var(--color-bg); color: var(--color-text-muted); }

.status-chip {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 3px 10px;
  border-radius: 10px;
  font-size: 11px; font-weight: 600;
  background: var(--color-bg);
  color: var(--color-text);
}
.status-chip::before {
  content: ''; width: 6px; height: 6px;
  border-radius: 50%;
  background: var(--color-text);
}
.status-chip.active {
  background: var(--color-primary);
  color: var(--color-text);
}
.status-chip.active::before { background: var(--color-primary); }

.role-chip {
  display: inline-block;
  padding: 3px 10px;
  border-radius: 10px;
  font-size: 11px; font-weight: 600;
}
.role-chip.admin { background: var(--color-bg); color: var(--color-text-muted); }
.role-chip.user { background: var(--color-bg); color: var(--color-text-muted); }

.date-cell { white-space: nowrap; font-size: 12px; color: var(--color-text-muted); }

.actions-cell { white-space: nowrap; }
.act-btn {
  padding: 5px 12px;
  border: 1px solid var(--color-border);
  border-radius: 8px;
  background: var(--color-bg);
  color: var(--color-text-secondary);
  font-size: 12px;
  cursor: pointer;
  margin-right: 6px;
  transition: all 0.15s;
  font-weight: 500;
}
.act-btn:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
  background: var(--color-sakura-light);
}
.act-btn.danger:hover {
  border-color: var(--color-text);
  color: var(--color-text);
  background: var(--color-bg);
}
.reset-btn {
  display: inline-flex; align-items: center; gap: 4px;
}
.spinner-sm {
  width: 12px; height: 12px;
  border: 2px solid var(--color-border);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
  display: inline-block;
}
@keyframes spin {
  to { transform: rotate(360deg); }
}
.self-tag { color: var(--color-text-muted); font-size: 12px; }

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

.error-msg {
  padding: 12px 20px; margin: 0;
  color: var(--color-error); font-size: 13px; text-align: center;
}

.empty-msg, .loading-msg {
  padding: 40px 20px; text-align: center;
  color: var(--color-text-muted);
  font-size: 13px;
}

@media (max-width: 768px) {
  .search-box { margin-left: 0; width: 100%; }
  .search-input { flex: 1; }
}
</style>
