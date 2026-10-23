import { clerkPlugin } from '@clerk/vue';
import { createApp } from 'vue'
import { createPinia } from 'pinia'
import router from './router'
import App from './App.vue'
import { installClerkBridge } from './utils/clerk'
import './assets/styles/base.css'

const PUBLISHABLE_KEY = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;

const app = createApp(App)
app.use(createPinia())
if (PUBLISHABLE_KEY) {app.use(clerkPlugin, {
  publishableKey: PUBLISHABLE_KEY,
  appearance: {
    variables: {
      colorPrimary: '#ff7daf',
      colorText: '#3d2b31',
      colorBackground: '#ffffff',
      borderRadius: '0.5rem',
    },
  },
});
}
// Capture the Clerk composables before anything can read auth state
installClerkBridge(app)
app.use(router)
app.mount('#app')
