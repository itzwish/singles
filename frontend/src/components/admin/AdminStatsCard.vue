<script setup lang="ts">
import type { Component } from 'vue'

defineProps<{
  icon: Component
  label: string
  value: number
  subtitle: string
}>()
</script>

<template>
  <div class="stat-card">
    <div class="card-icon-box">
      <component :is="icon" :size="22" />
    </div>
    <div class="card-body">
      <span class="card-value">{{ value.toLocaleString() }}</span>
      <span class="card-label">{{ label }}</span>
    </div>
    <div class="card-footer">
      <span class="card-sub">{{ subtitle }}</span>
    </div>
  </div>
</template>

<style scoped>
.stat-card {
  position: relative;
  background: var(--color-surface);
  border-radius: 16px;
  padding: 20px;
  overflow: hidden;
  border: 1px solid var(--color-border);
  transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
  cursor: default;
}
.stat-card:hover {
  transform: translateY(-2px);
}

.card-body {
  display: flex;
  align-items: center;
  gap: 14px;
  position: relative;
  z-index: 1;
}

.card-icon-box {
  width: 46px; height: 46px;
  border-radius: 10px;
  display: flex; align-items: center; justify-content: center;
  flex-shrink: 0;
}

.card-info {
  display: flex; flex-direction: column;
  min-width: 0;
}

.card-value {
  font-family: var(--font-heading);
  font-size: 28px;
  font-weight: 800;
  color: var(--color-text);
  line-height: 1.1;
  letter-spacing: -1px;
}

.card-label {
  font-size: 12px;
  color: var(--color-text-muted);
  margin-top: 2px;
  font-weight: 500;
}

.card-footer {
  margin-top: 14px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
  position: relative; z-index: 1;
}

.card-sub {
  font-size: 11px;
  color: var(--color-text-muted);
  font-weight: 500;
}

@media (max-width: 768px) {
  .stat-card { padding: 16px; }
}
</style>
