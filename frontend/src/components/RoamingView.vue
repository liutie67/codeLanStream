<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import type { MediaItem, MediaType } from '../api/types'
import { fetchRandom, getStreamUrl, toggleFavorite, toggleDelete } from '../api/client'
import { useSwipe, type SwipeDirection } from '../composables/useSwipe'
import TypeFilter from './TypeFilter.vue'
import VideoProgress from './VideoProgress.vue'

const emit = defineEmits<{ close: [] }>()

const items = ref<MediaItem[]>([])
const currentIndex = ref(0)
const loadedIds = ref<Set<string>>(new Set())
const mediaType = ref<MediaType | null>(null)
const hideMarked = ref(false)
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
const videoPaused = ref(true)
const lastAction = ref<{ itemId: string; action: 'favorite' | 'delete' } | null>(null)

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
    setTimeout(() => { phase.value = 'idle' }, 200)
  },
  threshold: 100,
})

async function handleSwipe(direction: SwipeDirection) {
  if (isLocked.value) return
  isLocked.value = true
  phase.value = 'animating'

  const vh = window.innerHeight
  const dur = 200

  if (direction === 'up') {
    // Confirm last action (no longer undoable)
    lastAction.value = null
    if (currentIndex.value >= items.value.length - 1) {
      if (hasMore.value) await loadMore()
      if (currentIndex.value >= items.value.length - 1) {
        offsetY.value = 0
        setTimeout(() => { phase.value = 'idle'; isLocked.value = false }, dur)
        return
      }
    }
    offsetY.value = -vh
  } else if (direction === 'down') {
    if (currentIndex.value <= 0) {
      offsetY.value = 0
      setTimeout(() => { phase.value = 'idle'; isLocked.value = false }, dur)
      return
    }
    // Undo last action when going back
    if (lastAction.value) {
      const { itemId, action } = lastAction.value
      lastAction.value = null
      const undoFn = action === 'favorite' ? toggleFavorite : toggleDelete
      undoFn(itemId).then(updated => {
        const idx = items.value.findIndex(i => i.id === updated.id)
        if (idx !== -1) items.value[idx] = updated
      }).catch(() => {})
    }
    offsetY.value = vh
  } else if (direction === 'right' || direction === 'left') {
    // Fire action immediately, don't await
    if (direction === 'right' && current.value) {
      lastAction.value = { itemId: current.value.id, action: 'favorite' }
      toggleFavorite(current.value.id).then(updated => {
        const idx = items.value.findIndex(i => i.id === updated.id)
        if (idx !== -1) items.value[idx] = updated
      }).catch(() => {})
    } else if (direction === 'left' && current.value) {
      lastAction.value = { itemId: current.value.id, action: 'delete' }
      toggleDelete(current.value.id).then(updated => {
        const idx = items.value.findIndex(i => i.id === updated.id)
        if (idx !== -1) items.value[idx] = updated
      }).catch(() => {})
    }
    // Skip slide animation — switch instantly
    phase.value = 'dragging'
    offsetX.value = 0
    currentIndex.value++
    await new Promise(r => requestAnimationFrame(r))
    phase.value = 'idle'
    isLocked.value = false
    return
  }

  // Wait for slide animation (up/down only)
  await new Promise(r => setTimeout(r, dur))

  // Advance index (disable transition to avoid re-animation)
  phase.value = 'dragging'
  if (direction === 'down') currentIndex.value--
  else currentIndex.value++

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
    const res = await fetchRandom(
      20, [...loadedIds.value], mediaType.value,
      hideMarked.value ? false : null,
      hideMarked.value ? false : null,
    )
    for (const item of res.items) loadedIds.value.add(item.id)
    items.value.push(...res.items)
    if (res.items.length < 20) hasMore.value = false
  } finally {
    loading.value = false
  }
}

function toggleHideMarked() {
  hideMarked.value = !hideMarked.value
  items.value = []
  loadedIds.value = new Set()
  currentIndex.value = 0
  hasMore.value = true
  loadMore()
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
    const wantMuted = isMuted.value
    videoEl.value.muted = true
    videoEl.value.volume = userVolume.value || 1
    try {
      await videoEl.value.play()
      videoEl.value.muted = wantMuted
      videoPaused.value = false
    } catch { /* autoplay blocked */ }
  }
  if (currentIndex.value >= items.value.length - 5) loadMore()
})

function onVolumeChange() {
  if (!videoEl.value) return
  isMuted.value = videoEl.value.muted
  userVolume.value = videoEl.value.volume
}

// Click left/right blank area to delete/favorite (desktop only)
function handleClick(e: MouseEvent) {
  if (isLocked.value || !current.value) return
  const target = e.target as HTMLElement
  if (target.tagName === 'IMG' || target.tagName === 'VIDEO') return
  if (e.clientX < window.innerWidth / 2) handleSwipe('left')   // delete
  else handleSwipe('right')                                      // favorite
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
  <div
    class="fixed inset-0 z-50 text-white overflow-hidden select-none"
    :style="{
      touchAction: 'none',
      background: current?.is_deleted && current?.is_favorited
        ? 'linear-gradient(to right, rgba(239,68,68,1) 50%, rgba(234,179,8,1) 50%)'
        : current?.is_deleted ? 'rgba(239,68,68,1)'
        : current?.is_favorited ? 'rgba(234,179,8,1)'
        : 'black',
    }"
  >
    <!-- Top bar -->
    <header class="absolute top-0 inset-x-0 z-10 flex items-center justify-between px-4 py-3">
      <div class="flex items-center gap-2">
        <button @click="emit('close')" class="w-8 h-8 flex items-center justify-center rounded-full bg-white/10 text-white/70 hover:text-white transition-colors">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
        <button
          @click="toggleHideMarked"
          class="h-8 px-2.5 flex items-center gap-1 rounded-full text-xs transition-colors"
          :class="hideMarked ? 'bg-blue-500/80 text-white' : 'bg-white/10 text-white/50 hover:text-white/80'"
          :title="hideMarked ? '显示全部' : '隐藏已收藏/已删除'"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path v-if="hideMarked" stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.5 10.5a3 3 0 004.243 4.243m0 0l1.536-1.536M6.75 6.75a7.5 7.5 0 009.743 9.743"/>
            <path v-if="hideMarked" stroke-linecap="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            <path v-if="!hideMarked" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
            <path v-if="!hideMarked" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
          </svg>
        </button>
      </div>
      <TypeFilter :current="mediaType" @change="setMediaType" />
      <span class="text-xs text-white/50 tabular-nums w-12 text-right">{{ currentIndex + 1 }}</span>
    </header>

    <!-- Card stack -->
    <div ref="containerRef" class="absolute inset-0" @click="handleClick">
      <!-- Previous item (above viewport) -->
      <div
        v-if="prevItem"
        class="absolute inset-0 flex items-center justify-center p-4 pt-16 pb-8"
        :style="{
          transform: `translateY(calc(-100% + ${offsetY}px))`,
          transition: hasTransition ? 'transform 200ms ease-out' : 'none',
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
          transition: hasTransition ? 'transform 200ms ease-out' : 'none',
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
          class="max-w-full max-h-full rounded-lg"
          @click.stop="videoEl && (videoEl.paused ? videoEl.play() : videoEl.pause())"
          @pause="videoPaused = true"
          @play="videoPaused = false"
          @volumechange="onVolumeChange"
        />
        <div
          v-if="current.media_type === 'video' && videoPaused"
          class="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <div class="w-20 h-20 rounded-full bg-black/40 flex items-center justify-center">
            <svg class="w-10 h-10 text-white ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
          </div>
        </div>
      </div>

      <!-- Next item (below viewport) -->
      <div
        v-if="nextItem"
        class="absolute inset-0 flex items-center justify-center p-4 pt-16 pb-8"
        :style="{
          transform: `translateY(calc(100% + ${offsetY}px))`,
          transition: hasTransition ? 'transform 200ms ease-out' : 'none',
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

    <!-- Bottom info + progress -->
    <div v-if="current" class="absolute bottom-0 inset-x-0 z-10 px-4 pb-4" @pointerdown.stop @click.stop @touchstart.stop>
      <VideoProgress v-if="current.media_type === 'video'" :video="videoEl" />
      <p class="text-sm text-white/60 text-center truncate">{{ current.file_path.split(/[/\\]/).pop() }}</p>
    </div>
  </div>
</template>
