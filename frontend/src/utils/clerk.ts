import { shallowRef, watch } from 'vue'
import type { App } from 'vue'
import { useAuth, useUser } from '@clerk/vue'

type AuthState = ReturnType<typeof useAuth>
type UserState = ReturnType<typeof useUser>

export interface ClerkUserInfo {
  id: string
  username: string | null
  fullName: string | null
  imageUrl: string
  /** False when Clerk would only serve its generated identicon. */
  hasImage: boolean
  email: string | null
}

const authState = shallowRef<AuthState | null>(null)
const userState = shallowRef<UserState | null>(null)

/**
 * Capture the Clerk composables once, at app level.
 *
 * `useAuth()` needs an injection context, so it is called through
 * `app.runWithContext()` right after the Clerk plugin is installed. The
 * captured objects hold reactive refs, which lets the app read Clerk state
 * from places that are not components — axios interceptors, Pinia stores and
 * router guards.
 */
export function installClerkBridge(app: App): void {
  authState.value = app.runWithContext(() => useAuth())
  userState.value = app.runWithContext(() => useUser())
}

/** The raw reactive Clerk auth state, or null before the bridge is installed. */
export function clerkAuth(): AuthState | null {
  return authState.value
}

/** The raw reactive Clerk user state, or null before the bridge is installed. */
export function clerkUserState(): UserState | null {
  return userState.value
}

export function clerkIsLoaded(): boolean {
  return !!authState.value?.isLoaded.value
}

export function clerkIsSignedIn(): boolean {
  return !!authState.value?.isSignedIn.value
}

export function clerkUserId(): string | null {
  return authState.value?.userId.value ?? null
}

export function clerkUser(): ClerkUserInfo | null {
  const u = userState.value?.user.value
  if (!u) return null
  return {
    id: u.id,
    username: u.username ?? null,
    fullName: u.fullName ?? null,
    imageUrl: u.imageUrl ?? '',
    hasImage: !!u.hasImage,
    email: u.primaryEmailAddress?.emailAddress ?? null,
  }
}

/** A fresh Clerk session token, or null when nobody is signed in. */
export async function clerkGetToken(): Promise<string | null> {
  const getToken = authState.value?.getToken.value
  if (!getToken) return null
  return (await getToken()) ?? null
}

/** Sign the current Clerk user out. */
export async function clerkSignOut(): Promise<void> {
  const signOut = authState.value?.signOut.value
  if (!signOut) return
  await signOut()
}

/**
 * Resolves once Clerk has finished loading.
 * Returns false when the timeout elapses first.
 */
export function waitForClerkReady(timeoutMs = 15000): Promise<boolean> {
  const state = authState.value
  if (!state) return Promise.resolve(false)
  if (state.isLoaded.value) return Promise.resolve(true)

  return new Promise<boolean>((resolve) => {
    let settled = false
    let stop: (() => void) | null = null
    let timer: ReturnType<typeof setTimeout> | null = null

    const finish = (ok: boolean) => {
      if (settled) return
      settled = true
      if (timer) clearTimeout(timer)
      stop?.()
      resolve(ok)
    }

    timer = setTimeout(() => finish(false), timeoutMs)
    stop = watch(
      () => state.isLoaded.value,
      (loaded) => {
        if (loaded) finish(true)
      },
    )
  })
}
