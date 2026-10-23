import axios from 'axios'
import { clerkGetToken, clerkIsSignedIn } from './clerk'

const api = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Instance used for file uploads (no Content-Type, so the browser sets the multipart boundary itself)
const uploadApi = axios.create({
  baseURL: '/api/v1',
  timeout: 60000,
})

const LEGACY_ACCESS_KEY = 'access_token'
const LEGACY_REFRESH_KEY = 'refresh_token'

/** True when a pre-Clerk session token is still around. */
export function hasLegacyToken(): boolean {
  return !!localStorage.getItem(LEGACY_ACCESS_KEY)
}

/** Drop every trace of the pre-Clerk session. */
export function clearLegacyTokens(): void {
  localStorage.removeItem(LEGACY_ACCESS_KEY)
  localStorage.removeItem(LEGACY_REFRESH_KEY)
  localStorage.removeItem('is_admin')
}

/**
 * The credential sent to the API.
 *
 * A Clerk session token wins; the legacy token is only used while somebody
 * signs in with the old password form, which still works until the accounts
 * are imported into Clerk.
 */
export async function resolveAuthToken(): Promise<string | null> {
  try {
    const clerkToken = await clerkGetToken()
    if (clerkToken) return clerkToken
  } catch {
    // Clerk is unavailable — fall back to the legacy token
  }
  return localStorage.getItem(LEGACY_ACCESS_KEY)
}

function addAuthInterceptor(instance: ReturnType<typeof axios.create>) {
  // Request interceptor: inject the session token automatically
  instance.interceptors.request.use(async (config) => {
    const token = await resolveAuthToken()
    if (token) {
      config.headers.Authorization = `Bearer ${token}`
    }
    return config
  })

  // Response interceptor: on 401 try to refresh the legacy token, otherwise
  // clear it and go to the sign-in page.
  // A 401 from the login/register endpoints means bad credentials — do not redirect
  instance.interceptors.response.use(
    (res) => res,
    async (error) => {
      const original = error.config
      if (error.response?.status === 401 && original && !original._retry) {
        const url = original.url || ''
        if (url.includes('/auth/login') || url.includes('/auth/register') || url.includes('/auth/refresh')) {
          return Promise.reject(error)
        }
        original._retry = true
        const refreshToken = localStorage.getItem(LEGACY_REFRESH_KEY)
        if (refreshToken) {
          try {
            const { data } = await axios.post('/api/v1/auth/refresh', { refresh_token: refreshToken })
            localStorage.setItem(LEGACY_ACCESS_KEY, data.access_token)
            localStorage.setItem(LEGACY_REFRESH_KEY, data.refresh_token)
            original.headers = original.headers ?? {}
            original.headers.Authorization = `Bearer ${data.access_token}`
            return instance(original)
          } catch {
            // Refresh failed, clear and redirect
          }
        }
        clearLegacyTokens()
        if (!clerkIsSignedIn()) {
          window.location.href = '/sign-in'
        }
        return Promise.reject(error)
      }
      return Promise.reject(error)
    }
  )
}

addAuthInterceptor(api)
addAuthInterceptor(uploadApi)

export default api
export { uploadApi }
