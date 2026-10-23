<script setup lang="ts">
import { SignIn } from '@clerk/vue'
</script>

<template>
  <div class="auth-view">
    <div class="auth-card">
      <div class="auth-header">
        <span class="brand-icon">🌸</span>
        <h1 class="brand-text">Easy Single</h1>
      </div>

      <div class="clerk-wrap">
        <SignIn
          sign-in-url="/sign-in"
          sign-up-url="/sign-up"
          fallback-redirect-url="/"
        />
      </div>
    </div>
  </div>
</template>

<style scoped>
.auth-view {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 24px;
  background: var(--color-bg, #fdf7f9);
}

.auth-card {
  width: 400px;
  max-width: 100%;
  background: var(--color-surface);
  border-radius: var(--radius-lg);
  border: 1px solid var(--color-border);
  padding: 32px 28px 24px;
  box-shadow: var(--shadow-sm);
}

.auth-header {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin-bottom: 20px;
}

.brand-icon { font-size: 24px; }

.brand-text {
  font-family: var(--font-heading);
  font-size: var(--text-lg);
  font-weight: 700;
  color: var(--color-primary-dark);
  letter-spacing: 2px;
}

.clerk-wrap {
  display: flex;
  justify-content: center;
}
</style>
