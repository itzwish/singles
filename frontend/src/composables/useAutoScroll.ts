import { ref, type Ref, nextTick } from 'vue'

const SCROLL_CHECK_INTERVAL = 100

export function useAutoScroll(containerRef: Ref<HTMLElement | null>) {
  const isUserScrolledUp = ref(false)
  let lastCheck = 0
  let checkTimeout = 0

  function scrollToBottom(smooth = true) {
    const el = containerRef.value
    if (!el) return
    el.scrollTo({
      top: el.scrollHeight,
      behavior: smooth ? 'smooth' : 'instant',
    })
  }

  function checkScrollPosition() {
    const el = containerRef.value
    if (!el) return
    const now = Date.now()
    if (now - lastCheck < SCROLL_CHECK_INTERVAL) {
      if (checkTimeout) clearTimeout(checkTimeout)
      checkTimeout = setTimeout(checkScrollPosition, SCROLL_CHECK_INTERVAL - (now - lastCheck))
      return
    }
    lastCheck = now
    isUserScrolledUp.value = el.scrollHeight - el.scrollTop - el.clientHeight > 100
  }

  function onNewContent() {
    nextTick(() => {
      if (!isUserScrolledUp.value) {
        scrollToBottom()
      }
    })
  }

  function throttleCheck() {
    checkScrollPosition()
    checkTimeout = setTimeout(checkScrollPosition, SCROLL_CHECK_INTERVAL)
  }

  return { scrollToBottom, onNewContent, isUserScrolledUp, checkScrollPosition, throttleCheck }
}
