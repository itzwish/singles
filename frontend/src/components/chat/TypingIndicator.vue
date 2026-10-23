<template>
  <div class="typing" aria-label="Typing">
    <span></span><span></span><span></span>
  </div>
</template>

<style scoped>
.typing {
  display: flex;
  gap: 5px;
  padding: 10px 14px;
  align-self: flex-start;
  align-items: center;
  margin-left: 46px;
}
.typing span {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--color-bubble-ai-ink);
  opacity: 0.55;
  animation: bounce 1.3s infinite ease-in-out both;
}
.typing span:nth-child(1) { animation-delay: -0.26s; }
.typing span:nth-child(2) { animation-delay: -0.13s; }

@keyframes bounce {
  0%, 80%, 100% { transform: translateY(0); opacity: 0.35; }
  40%           { transform: translateY(-3px); opacity: 0.9; }
}

@media (prefers-reduced-motion: reduce) {
  .typing span { animation: none; opacity: 0.55; }
}
</style>
