import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'

// Routes that do not need a session
const PUBLIC_PATHS = ['/sign-in', '/sign-up', '/auth']

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: () => import('@/views/HomeView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/auth',
      name: 'auth',
      redirect: '/sign-in',
    },
    {
      path: '/chat/:characterId',
      name: 'chat',
      component: () => import('@/views/ChatView.vue'),
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/character/:characterId/edit',
      name: 'characterEdit',
      component: () => import('@/views/CharacterEditView.vue'),
      props: true,
      meta: { requiresAuth: true },
    },
    {
      path: '/profile',
      name: 'profile',
      component: () => import('@/views/ProfileView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: '/admin',
      name: 'admin',
      component: () => import('@/views/AdminView.vue'),
      meta: { requiresAuth: true },
    },
    {
      path: "/sign-in",
      component: () => import("@/views/sign-in.vue"),
    },
    {
      path: "/sign-up",
      component: () => import("@/views/sign-up.vue"),
    },
    {
      // Anything unknown (including the old /auth/legacy bookmark) goes home
      // and is then handled by the auth guard.
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

router.beforeEach(async (to) => {
  const auth = useAuthStore()

  // Clerk owns the session, so the first check has to wait for it to load
  if (!auth.authChecked || (auth.clerkSignedIn && !auth.sessionValid)) {
    await auth.checkAuth()
  }

  const signedIn = auth.isLoggedIn && auth.sessionValid

  if (PUBLIC_PATHS.includes(to.path)) {
    if (signedIn && (to.path === '/sign-in' || to.path === '/auth')) return '/'
    return true
  }

  if (!signedIn) return '/sign-in'
  if (to.path === '/admin' && !auth.isAdmin) return '/'
  return true
})

export default router
