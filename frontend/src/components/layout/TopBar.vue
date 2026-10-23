<script setup lang="ts">
import { useRouter } from 'vue-router'
import { ArrowLeft, Shield, Settings } from 'lucide-vue-next'
import { storeToRefs } from 'pinia'
import { useAuthStore } from '@/stores/auth'

defineProps<{
  title?: string
  showBack?: boolean
}>()

defineEmits<{
  back: []
}>()

const router = useRouter()
const auth = useAuthStore()
const { guestName, userAvatar, isAdmin } = storeToRefs(auth)

function goProfile() {
  router.push('/profile')
}

function goAdmin() {
  router.push('/admin')
}
</script>

<template>
  <header class="top-bar">
    <div class="top-bar-left">
      <button v-if="showBack" class="back-btn" @click="$emit('back')">
        <ArrowLeft :size="20" />
      </button>
      <div class="brand" v-else>
        <!-- Five petals, drawn: the mark carries the name's flower in one colour. -->
        <svg class="brand-mark" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <g fill="currentColor">
            <ellipse cx="12" cy="6.4" rx="3.1" ry="4.6" />
            <ellipse cx="12" cy="6.4" rx="3.1" ry="4.6" transform="rotate(72 12 12)" />
            <ellipse cx="12" cy="6.4" rx="3.1" ry="4.6" transform="rotate(144 12 12)" />
            <ellipse cx="12" cy="6.4" rx="3.1" ry="4.6" transform="rotate(216 12 12)" />
            <ellipse cx="12" cy="6.4" rx="3.1" ry="4.6" transform="rotate(288 12 12)" />
          </g>
          <circle cx="12" cy="12" r="1.7" fill="var(--color-bg)" />
        </svg>
        <span class="brand-text">Easy Single</span>
      </div>
      <h1 class="page-title" v-if="title">{{ title }}</h1>
    </div>

    <div class="top-bar-center">
      <slot name="actions" />
    </div>

    <div class="top-bar-right">
      <button v-if="isAdmin" class="admin-btn" @click="goAdmin" title="Admin panel">
        <Shield :size="18" />
      </button>
      <button class="admin-btn" @click="goProfile" title="Your profile">
        <Settings :size="18" />
      </button>
      <!-- One account chip everywhere: initials on the brand tint, or the
           picture the user uploaded. Account actions live on the profile page. -->
      <button class="user-avatar" type="button" @click="goProfile" title="Your profile" aria-label="Your profile">
        <img v-if="userAvatar" :src="auth.getUserAvatarUrl()" class="avatar-img" alt="" />
        <span v-else>{{ guestName?.[0]?.toUpperCase() || '?' }}</span>
      </button>
    </div>
  </header>
</template>

<style scoped>
.top-bar {
  height: 52px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 28px;
  background: var(--color-bg);
  border-bottom: 1px solid var(--color-border);
  flex-shrink: 0;
}

.top-bar-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 9px;
}
.brand-mark {
  width: 20px;
  height: 20px;
  color: var(--color-primary);
  flex-shrink: 0;
}
.brand-text {
  font-family: var(--font-heading);
  font-size: 16px;
  font-weight: 600;
  color: var(--color-text);
}

.back-btn {
  width: 36px; height: 36px;
  border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  color: var(--color-text-secondary);
  border: none; background: transparent; cursor: pointer;
  transition: all var(--duration-fast) var(--ease-smooth);
}
.back-btn:hover { background: var(--color-sakura); color: var(--color-primary); }

.page-title {
  font-family: var(--font-heading);
  font-size: var(--text-base);
  font-weight: 600;
  color: var(--color-text);
}

.top-bar-center {
  display: flex; align-items: center; gap: 8px;
  flex: 1; justify-content: center;
}

.top-bar-right {
  display: flex; align-items: center; gap: 8px;
}


.admin-btn {
  width: 32px; height: 32px;
  border-radius: var(--radius-xs);
  border: 0;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  display: flex; align-items: center; justify-content: center;
  transition: background-color 140ms var(--ease-smooth), color 140ms var(--ease-smooth);
}
.admin-btn:hover {
  background: var(--color-sakura);
  color: var(--color-text);
}
.admin-btn:focus-visible {
  outline: 2px solid var(--color-primary-dark);
  outline-offset: 2px;
}

.user-avatar {
  width: 30px; height: 30px;
  padding: 0;
  border: 0;
  border-radius: var(--radius-sm);
  background: var(--color-sakura);
  display: flex; align-items: center; justify-content: center;
  color: var(--color-primary-dark);
  font-family: var(--font-heading);
  font-size: 13px; font-weight: 600;
  cursor: pointer; overflow: hidden;
  transition: background-color 140ms var(--ease-smooth);
}
.user-avatar:hover { background: var(--color-primary-light); }
.user-avatar:focus-visible { outline: 2px solid var(--color-action); outline-offset: 2px; }
.avatar-img {
  width: 100%; height: 100%;
  border-radius: inherit; object-fit: cover;
}

@media (max-width: 768px) {
  .top-bar {
    padding: 0 16px;
  }
  .brand-text {
    font-size: 15px;
  }
  .page-title {
    font-size: var(--text-sm);
  }
}
</style>
