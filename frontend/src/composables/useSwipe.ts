import { ref, onUnmounted, type Ref } from 'vue'

export type SwipeDirection = 'up' | 'down' | 'left' | 'right'

interface SwipeOptions {
  onSwipe: (direction: SwipeDirection) => void
  onDragUpdate?: (offset: { x: number; y: number }) => void
  onDragEnd?: () => void
  threshold?: number
}

export function useSwipe(target: Ref<HTMLElement | undefined>, options: SwipeOptions) {
  const threshold = options.threshold ?? 100
  const isDragging = ref(false)

  let startX = 0
  let startY = 0
  let startTime = 0
  let lastOffset = { x: 0, y: 0 }
  let lockedAxis: 'x' | 'y' | null = null
  let wheelTimer: ReturnType<typeof setTimeout> | null = null

  function onTouchStart(e: TouchEvent) {
    const t = e.touches[0]
    startX = t.clientX
    startY = t.clientY
    startTime = Date.now()
    lockedAxis = null
    lastOffset = { x: 0, y: 0 }
    isDragging.value = true
  }

  function onTouchMove(e: TouchEvent) {
    if (!isDragging.value) return
    e.preventDefault()
    const t = e.touches[0]
    const dx = t.clientX - startX
    const dy = t.clientY - startY

    if (!lockedAxis) {
      if (Math.abs(dx) > 10 || Math.abs(dy) > 10) {
        lockedAxis = Math.abs(dx) > Math.abs(dy) ? 'x' : 'y'
      }
    }

    const offset = { x: 0, y: 0 }
    if (lockedAxis === 'x') offset.x = dx
    else if (lockedAxis === 'y') offset.y = dy

    lastOffset = offset
    options.onDragUpdate?.(offset)
  }

  function onTouchEnd() {
    if (!isDragging.value) return
    isDragging.value = false

    const absX = Math.abs(lastOffset.x)
    const absY = Math.abs(lastOffset.y)
    const duration = Date.now() - startTime
    const velocity = duration > 0 ? Math.max(absX, absY) / duration : 0

    const isFastSwipe = velocity > 0.5

    if (lockedAxis === 'y' && (absY > threshold || isFastSwipe)) {
      options.onSwipe(lastOffset.y < 0 ? 'up' : 'down')
      return // consumer handles animation and offset reset
    }
    if (lockedAxis === 'x' && (absX > threshold || isFastSwipe)) {
      options.onSwipe(lastOffset.x < 0 ? 'left' : 'right')
      return
    }

    options.onDragEnd?.()
  }

  function onWheel(e: WheelEvent) {
    e.preventDefault()
    if (wheelTimer) return
    if (Math.abs(e.deltaY) < 10) return

    options.onSwipe(e.deltaY > 0 ? 'up' : 'down')
    wheelTimer = setTimeout(() => { wheelTimer = null }, 400)
  }

  function bind(el: HTMLElement) {
    el.addEventListener('touchstart', onTouchStart, { passive: true })
    el.addEventListener('touchmove', onTouchMove, { passive: false })
    el.addEventListener('touchend', onTouchEnd, { passive: true })
    el.addEventListener('wheel', onWheel, { passive: false })
  }

  function unbind(el: HTMLElement) {
    el.removeEventListener('touchstart', onTouchStart)
    el.removeEventListener('touchmove', onTouchMove)
    el.removeEventListener('touchend', onTouchEnd)
    el.removeEventListener('wheel', onWheel)
  }

  function attach() {
    if (target.value) bind(target.value)
  }

  function detach() {
    if (target.value) unbind(target.value)
  }

  onUnmounted(detach)

  return { isDragging, attach, detach }
}
