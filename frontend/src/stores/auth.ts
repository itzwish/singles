import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import api, { clearLegacyTokens, hasLegacyToken } from '@/utils/http'
import { clerkAuth, clerkSignOut, clerkUser, waitForClerkReady } from '@/utils/clerk'

const GUEST_EMAIL = 'guest@easy-single.local'

export const useAuthStore = defineStore('auth', () => {
  const guestName = ref('')
  const userAvatar = ref<string | null>(null)
  const userEmail = ref('')
  const authChecked = ref(false) // whether the startup token check has finished
  const sessionValid = ref(false) // whether the backend accepted the session

  const isAdmin = ref(false)
  const hasApiKey = ref(false)
  const apiBaseUrl = ref<string | null>(null)
  const apiModel = ref<string | null>(null)
  const showApiKeyWarning = ref(false)
  const userAvatarVersion = ref(0)

  // Clerk state, read through the app-level bridge so it stays reactive
  const clerkSignedIn = computed(() => !!clerkAuth()?.isSignedIn.value)
  // The pre-Clerk session, tracked in a ref because localStorage is not
  // reactive and a computed would keep the first value it saw.
  const legacySignedIn = ref(false)

  const isLoggedIn = computed(() => clerkSignedIn.value || legacySignedIn.value)
  const hasToken = () => isLoggedIn.value

  function getUserAvatarUrl(): string {
    if (!userAvatar.value) return ''
    return userAvatarVersion.value > 0 ? `${userAvatar.value}?v=${userAvatarVersion.value}` : userAvatar.value
  }

  async function loadUserInfo() {
    const res = await api.get<{ email: string; username: string; avatar_url: string | null; is_admin: boolean; has_api_key: boolean; api_base_url: string | null; api_model: string | null }>('/users/me')
    guestName.value = res.data.username || ''
    // The database row is the source of truth (it can hold an uploaded
    // avatar); a real Clerk profile picture is the fallback. Clerk's generated
    // identicon is not: the app draws initials in the brand tint instead.
    const clerkPic = clerkUser()
    userAvatar.value = res.data.avatar_url || (clerkPic?.hasImage ? clerkPic.imageUrl : null) || null
    userEmail.value = res.data.email || ''
    isAdmin.value = res.data.is_admin || false
    localStorage.setItem('is_admin', isAdmin.value ? '1' : '0')
    hasApiKey.value = res.data.has_api_key || false
    apiBaseUrl.value = res.data.api_base_url || null
    apiModel.value = res.data.api_model || null
  }

  /**
   * Resolve the current session.
   *
   * Clerk owns the session; the pre-Clerk token is only honoured while the
   * old accounts are still being migrated across.
   */
  async function checkAuth(): Promise<boolean> {
    await waitForClerkReady()
    sessionValid.value = false

    if (clerkSignedIn.value) {
      // A Clerk session supersedes any leftover legacy token
      clearLegacyTokens()
      legacySignedIn.value = false
      try {
        await loadUserInfo()
        sessionValid.value = true
      } catch {
        // The API may be unavailable (e.g. during deployment).
        // Trust Clerk's client-side session so the app still loads.
        sessionValid.value = true
      }
      authChecked.value = true
      return sessionValid.value
    }

    if (hasLegacyToken()) {
      try {
        await loadUserInfo()
        if (userEmail.value === GUEST_EMAIL) {
          // Drop the guest token and require a real sign-in
          clearLegacyTokens()
          legacySignedIn.value = false
          authChecked.value = true
          return false
        }
        legacySignedIn.value = true
        sessionValid.value = true
        authChecked.value = true
        return true
      } catch {
        clearLegacyTokens()
        legacySignedIn.value = false
        authChecked.value = true
        return false
      }
    }

    legacySignedIn.value = false
    authChecked.value = true
    return false
  }

  async function updateProfile(data: { username?: string; avatar_url?: string; api_key?: string; api_base_url?: string; api_model?: string }) {
    const res = await api.patch<{ username: string; avatar_url: string | null; has_api_key: boolean; api_base_url: string | null; api_model: string | null }>('/users/me', data)
    guestName.value = res.data.username || ''
    userAvatar.value = res.data.avatar_url
    hasApiKey.value = res.data.has_api_key || false
    apiBaseUrl.value = res.data.api_base_url || null
    apiModel.value = res.data.api_model || null
  }

  /** Sign out of Clerk and drop any legacy session. */
  async function logout() {
    try {
      await clerkSignOut()
    } catch {
      // The session may already be gone
    }
    clearLegacyTokens()
    legacySignedIn.value = false
    sessionValid.value = false
    guestName.value = ''
    userAvatar.value = null
    userEmail.value = ''
    isAdmin.value = false
  }

  function promptApiKey() {
    showApiKeyWarning.value = true
  }

  function dismissApiKeyWarning() {
    showApiKeyWarning.value = false
  }

  return { guestName, userAvatar, userEmail, authChecked, sessionValid, clerkSignedIn, legacySignedIn, isLoggedIn, isAdmin, hasToken, hasApiKey, apiBaseUrl, apiModel, showApiKeyWarning, userAvatarVersion, getUserAvatarUrl, checkAuth, loadUserInfo, updateProfile, logout, promptApiKey, dismissApiKeyWarning }
})
