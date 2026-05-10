<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import type { MediaItem, MediaType } from '../api/types'
import { fetchRandom, getStreamUrl, toggleFavorite, toggleDelete } from '../api/client'
import { useSwipe, type SwipeDirection } from '../composables/useSwipe'
import TypeFilter from './TypeFilter.vue'

const emit = defineEmits<{ close: [] }>()

const items = ref<MediaItem[]>([])
const currentIndex = ref(0)
const loadedIds = ref<Set<string>>(new Set())
const mediaType = ref<MediaType | null>(null)
const loading = ref(false)
const hasMore = ref(true)
const isLocked = ref(false)

// Phase: 'idle' = CSS transitions on, 'dragging' = no transitions, 'animating' = transitions on
const phase = ref<'idle' | 'dragging' | 'animating'>('idle')
const offsetY = ref(0)
const offsetX = ref(0)
const videoEl = ref<HTMLVideoElement | null>(null)
const isMuted = ref(true)
const userVolume = ref(0)

const current = computed(() => items.value[currentIndex.value])
const prevItem = computed(() => currentIndex.value > 0 ? items.value[currentIndex.value - 1] : null)
const nextItem = computed(() => currentIndex.value < items.value.length - 1 ? items.value[currentIndex.value + 1] : null)
const containerRef = ref<HTMLElement>()

const hasTransition = computed(() => phase.value !== 'dragging')

const { attach, detach } = useSwipe(containerRef, {
  onSwipe: handleSwipe,
  onDragUpdate: (offset) => {
    phase.value = 'dragging'
    offsetY.value = offset.y
    offsetX.value = offset.x
  },
  onDragEnd: () => {
    // Snap back with animation
    phase.value = 'animating'
    offsetY.value = 0
    offsetX.value = 0
    setTimeout(() => { phase.value = 'idle' }, 300)
  },
  threshold: 100,
})

async function handleSwipe(direction: SwipeDirection) {
  if (isLocked.value) return
  isLocked.value = true
  phase.value = 'animating'

  const vh = window.innerHeight

  if (direction === 'up') {
    if (currentIndex.value >= items.value.length - 1) {
      if (hasMore.value) await loadMore()
      if (currentIndex.value >= items.value.length - 1) {
        // No next item, snap back
        phase.value = 'animating'
        offsetY.value = 0
        setTimeout(() => { phase.value = 'idle'; isLocked.value = false }, 300)
        return
      }
    }
    // Animate current up, next slides in from below
    offsetY.value = -vh
  } else if (direction === 'down') {
    if (currentIndex.value <= 0) {
      phase.value = 'animating'
      offsetY.value = 0
      setTimeout(() => { phase.value = 'idle'; isLocked.value = false }, 300)
      return
    }
    offsetY.value = vh
  } else if (direction === 'right' || direction === 'left') {
    // Horizontal: animate off screen
    offsetX.value = direction === 'right' ? vh : -vh
  }

  // Wait for animation to complete
  await new Promise(r => setTimeout(r, 300))

  // Fire API call for horizontal actions
  if (direction === 'right' && current.value) {
    try {
      const updated = await toggleFavorite(current.value.id)
      const idx = items.value.findIndex(i => i.id === updated.id)
      if (idx !== -1) items.value[idx] = updated
    } catch { /* ignore */ }
  } else if (direction === 'left' && current.value) {
    try {
      const updated = await toggleDelete(current.value.id)
      const idx = items.value.findIndex(i => i.id === updated.id)
      if (idx !== -1) items.value[idx] = updated
    } catch { /* ignore */ }
  }

  // Advance index (disable transition to avoid re-animation)
  phase.value = 'dragging'
  if (direction === 'down') currentIndex.value--
  else currentIndex.value++ // up, left, right all go forward

  // Reset offset instantly (no transition)
  offsetY.value = 0
  offsetX.value = 0

  // Re-enable transitions after frame
  await new Promise(r => requestAnimationFrame(r))
  phase.value = 'idle'
  isLocked.value = false
}

async function loadMore() {
  if (loading.value || !hasMore.value) return
  loading.value = true
  try {
    const res = await fetchRandom(20, [...loadedIds.value], mediaType.value)
    for (const item of res.items) loadedIds.value.add(item.id)
    items.value.push(...res.items)
    if (res.items.length < 20) hasMore.value = false
  } finally {
    loading.value = false
  }
}

function setMediaType(type: MediaType | null) {
  mediaType.value = type
  items.value = []
  loadedIds.value = new Set()
  currentIndex.value = 0
  hasMore.value = true
  loadMore()
}

// Horizontal swipe feedback
const feedbackColor = computed(() => {
  if (offsetX.value > 30) return 'yellow'
  if (offsetX.value < -30) return 'red'
  return null
})

const feedbackOpacity = computed(() => Math.min(0.5, Math.abs(offsetX.value) / 200))

// Video auto-play + volume persistence
watch(current, async () => {
  await nextTick()
  if (videoEl.value) {
    videoEl.value.muted = isMuted.value
    videoEl.value.volume = userVolume.value
    try { await videoEl.value.play() } catch { /* autoplay blocked */ }
  }
  if (currentIndex.value >= items.value.length - 5) loadMore()
})

function onVolumeChange() {
  if (!videoEl.value) return
  isMuted.value = videoEl.value.muted
  userVolume.value = videoEl.value.volume
}

// Keyboard
function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') emit('close')
  else if (e.key === 'ArrowDown' || e.key === 'ArrowRight') handleSwipe('up')
  else if (e.key === 'ArrowUp' || e.key === 'ArrowLeft') handleSwipe('down')
  else if (e.key === 'f') handleSwipe('right')
  else if (e.key === 'd') handleSwipe('left')
}

onMounted(() => {
  attach()
  loadMore()
  window.addEventListener('keydown', onKeydown)
})

onUnmounted(() => {
  detach()
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black text-white overflow-hidden select-none" style="touch-action: none">
    <!-- Top bar -->
    <header class="absolute top-0 inset-x-0 z-10 flex items-center justify-between px-4 py-3">
      <button @click="emit('close')" class="w-8 h-8 flex items-center justify-center rounded-full bg-white/10 text-white/70 hover:text-white transition-colors">
        <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
      </button>
      <TypeFilter :current="mediaType" @change="setMediaType" />
      <span class="text-xs text-white/50 tabular-nums w-12 text-right">{{ currentIndex + 1 }}</span>
    </header>

    <!-- Card stack -->
    <div ref="containerRef" class="absolute inset-0">
      <!-- Previous item (above viewport) -->
      <div
        v-if="prevItem"
        class="absolute inset-0 flex items-center justify-center p-4 pt-16 pb-8"
        :style="{
          transform: `translateY(calc(-100% + ${offsetY}px))`,
          transition: hasTransition ? 'transform 300ms ease-out' : 'none',
        }"
      >
        <img
          v-if="prevItem.media_type === 'image'"
          :src="getStreamUrl(prevItem.id)"
          class="max-w-full max-h-full object-contain rounded-lg"
        />
        <video
          v-else
          :src="getStreamUrl(prevItem.id)"
          muted
          playsinline
          class="max-w-full max-h-full rounded-lg"
        />
      </div>

      <!-- Current item (centered, follows swipe) -->
      <div
        v-if="current"
        :key="current.id"
        class="absolute inset-0 flex items-center justify-center p-4 pt-16 pb-8"
        :style="{
          transform: `translate(${offsetX}px, ${offsetY}px)`,
          transition: hasTransition ? 'transform 300ms ease-out' : 'none',
        }"
      >
        <img
          v-if="current.media_type === 'image'"
          :src="getStreamUrl(current.id)"
          class="max-w-full max-h-full object-contain rounded-lg"
        />
        <video
          v-else
          ref="videoEl"
          :src="getStreamUrl(current.id)"
          autoplay
          muted
          loop
          playsinline
          controls
          class="max-w-full max-h-full rounded-lg"
          @volumechange="onVolumeChange"
        />
      </div>

      <!-- Next item (below viewport) -->
      <div
        v-if="nextItem"
        class="absolute inset-0 flex items-center justify-center p-4 pt-16 pb-8"
        :style="{
          transform: `translateY(calc(100% + ${offsetY}px))`,
          transition: hasTransition ? 'transform 300ms ease-out' : 'none',
        }"
      >
        <img
          v-if="nextItem.media_type === 'image'"
          :src="getStreamUrl(nextItem.id)"
          class="max-w-full max-h-full object-contain rounded-lg"
        />
        <video
          v-else
          :src="getStreamUrl(nextItem.id)"
          muted
          playsinline
          class="max-w-full max-h-full rounded-lg"
        />
      </div>

      <div v-if="!current && loading" class="absolute inset-0 flex items-center justify-center text-white/50">加载中...</div>
      <div v-if="!current && !loading && !hasMore" class="absolute inset-0 flex items-center justify-center text-white/50">已浏览全部</div>
    </div>

    <!-- Horizontal swipe feedback overlay -->
    <div
      v-if="feedbackColor"
      class="absolute inset-0 pointer-events-none flex items-center justify-center"
      :style="{ backgroundColor: feedbackColor === 'yellow' ? 'rgba(234,179,8,1)' : 'rgba(239,68,68,1)', opacity: feedbackOpacity }"
    >
      <svg v-if="feedbackColor === 'yellow'" class="w-20 h-20 text-white" :style="{ opacity: feedbackOpacity * 2 }" fill="currentColor" viewBox="0 0 24 24">
        <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z"/>
      </svg>
      <svg v-else class="w-20 h-20 text-white" :style="{ opacity: feedbackOpacity * 2 }" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
        <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z"/>
      </svg>
    </div>

    <!-- Bottom info -->
    <div v-if="current" class="absolute bottom-0 inset-x-0 z-10 px-4 pb-4">
      <p class="text-sm text-white/60 text-center truncate">{{ current.file_path.split(/[/\\]/).pop() }}</p>
    </div>
  </div>
</template>
