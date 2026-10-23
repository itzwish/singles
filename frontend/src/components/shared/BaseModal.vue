<script setup lang="ts">
defineProps<{ show: boolean; title?: string; closeOnOverlay?: boolean }>()
defineEmits<{ close: [] }>()
</script>

<template>
  <Teleport to="body">
    <transition name="modal-fade">
      <div v-if="show" class="modal-overlay" @click.self="closeOnOverlay !== false && $emit('close')">
        <transition name="modal-slide">
          <div v-if="show" class="modal-content">
            <div class="modal-header">
              <h3>{{ title }}</h3>
              <button class="modal-close" @click="$emit('close')">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" width="16" height="16"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
              </button>
            </div>
            <div class="modal-body">
              <slot />
            </div>
            <div class="modal-footer" v-if="$slots.footer">
              <slot name="footer" />
            </div>
          </div>
        </transition>
      </div>
    </transition>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  background: rgba(74,37,53,0.3);
}

/* A dialog is one of the few things allowed to float. */
.modal-content {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-lg);
  width: 460px; max-width: 92vw; max-height: 85vh;
  display: flex; flex-direction: column;
}

.modal-header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 18px 24px;
  border-bottom: 1px solid var(--color-border);
}
.modal-header h3 {
  font-size: 20px;
  font-weight: 600;
  font-family: var(--font-heading);
  color: var(--color-text);
}

.modal-close {
  width: 30px; height: 30px; border-radius: var(--radius-xs);
  display: flex; align-items: center; justify-content: center;
  color: var(--color-text-secondary);
  cursor: pointer; background: transparent; border: none;
  transition: background-color 140ms var(--ease-smooth), color 140ms var(--ease-smooth);
}
.modal-close:hover {
  background: var(--color-sakura);
  color: var(--color-text);
}
.modal-close:focus-visible {
  outline: 2px solid var(--color-action);
  outline-offset: 2px;
}

.modal-body {
  padding: 20px 24px;
  overflow-y: auto; flex: 1;
  font-family: var(--font-body);
}

.modal-footer {
  display: flex; justify-content: flex-end; gap: 8px;
  padding: 14px 24px;
  border-top: 1px solid var(--color-border);
}

@media (max-width: 480px) {
  .modal-content {
    width: 100%;
    max-width: 96vw;
    max-height: 90vh;
    border-radius: var(--radius);
  }
  .modal-header {
    padding: 14px 16px;
  }
  .modal-body {
    padding: 16px;
  }
  .modal-footer {
    padding: 12px 16px;
  }
}

/* ── Transitions ── */
.modal-fade-enter-active,
.modal-fade-leave-active {
  transition: opacity var(--duration) var(--ease-smooth);
}
.modal-fade-enter-from,
.modal-fade-leave-to { opacity: 0; }

.modal-slide-enter-active {
  transition: opacity 180ms var(--ease-smooth), transform 180ms var(--ease-smooth);
}
.modal-slide-leave-active {
  transition: opacity 140ms var(--ease-smooth), transform 140ms var(--ease-smooth);
}
.modal-slide-enter-from {
  opacity: 0; transform: translateY(10px);
}
.modal-slide-leave-to {
  opacity: 0; transform: translateY(-6px);
}
</style>
