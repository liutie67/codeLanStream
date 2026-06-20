<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted, onUnmounted } from 'vue'
import type { MediaItem, MediaType } from '../api/types'
import { fetchFeed, fetchRandom, getStreamUrl, getPreviewUrl, getThumbnailUrl, toggleFavorite, toggleDelete, toggleDamaged } from '../api/client'
import { useSwipe, type SwipeDirection } from '../composables/useSwipe'
import { useThumbnailMode } from '../composables/useThumbnailMode'
import TypeFilter from './TypeFilter.vue'
import VideoProgress from './VideoProgress.vue'
import {
  createDetachedVideoPreloader,
  createPreloadImage,
  releaseImageElement,
  releaseMediaElement,
  updateDetachedVideoPreload,
} from '../utils/mediaResource'

const emit = defineEmits<{ close: [] }>()

const { thumbMode } = useThumbnailMode()
type MarkAction = 'favorite' | 'delete' | 'damage'
type BrowseMode = 'random' | 'folder' | 'size'

const items = ref<MediaItem[]>([])
const currentIndex = ref(0)
const loadedIds = ref<Set<string>>(new Set())
const mediaType = ref<MediaType | null>(null)
const hideMarked = ref(false)
const loading = ref(false)
const hasMore = ref(true)
const isLocked = ref(false)
const browseMode = ref<BrowseMode>('random')
const orderedPage = ref(1)
const folderAnchor = ref<string | null>(null)
const folderAfter = ref<string | null>(null)
const folderStart = ref<string | null>(null)
const folderWrapped = ref(false)
const PRELOAD_COUNT = 4
const VIDEO_AUTO_PRELOAD_DISTANCE = 1
const LOAD_BATCH_SIZE = 20

// Phase: 'idle' = CSS transitions on, 'dragging' = no transitions, 'animating' = transitions on
const phase = ref<'idle' | 'dragging' | 'animating'>('idle')
const offsetY = ref(0)
const offsetX = ref(0)
const videoEl = ref<HTMLVideoElement | null>(null)
const isMuted = ref(true)
const userVolume = ref(0)
const videoPaused = ref(true)
const lastAction = ref<{ itemId: string; action: MarkAction } | null>(null)
const pendingKeyAction = ref<MarkAction | null>(null)
const playbackRate = ref(1)
const showHelp = ref(false)
const isDesktop = !('ontouchstart' in window)

const current = computed(() => items.value[currentIndex.value])
const prevItem = computed(() => currentIndex.value > 0 ? items.value[currentIndex.value - 1] : null)
const nextItem = computed(() => currentIndex.value < items.value.length - 1 ? items.value[currentIndex.value + 1] : null)
const preloadWindowItems = computed(() => {
  const start = currentIndex.value + 1
  return items.value.slice(start, start + PRELOAD_COUNT)
})
const containerRef = ref<HTMLElement>()
const browseModes: Array<{ mode: BrowseMode; label: string; title: string }> = [
  { mode: 'random', label: '随机', title: '当前: 随机刷取，点击切换到同文件夹连续' },
  { mode: 'folder', label: '文件夹', title: '当前: 同文件夹连续，点击切换到按大小倒序' },
  { mode: 'size', label: '大小', title: '当前: 按大小从大到小，点击切换到随机' },
]

const hasTransition = computed(() => phase.value !== 'dragging')
const currentBrowseMode = computed(() => (
  browseModes.find(item => item.mode === browseMode.value) || browseModes[0]
))
const currentBackground = computed(() => {
  if (!current.value) return 'black'
  if (current.value.is_damaged) return 'rgba(168,85,247,1)'
  if (current.value.is_deleted && current.value.is_favorited) {
    return 'linear-gradient(to right, rgba(239,68,68,1) 50%, rgba(234,179,8,1) 50%)'
  }
  if (current.value.is_deleted) return 'rgba(239,68,68,1)'
  if (current.value.is_favorited) return 'rgba(234,179,8,1)'
  return 'black'
})
const keyActionColor = computed(() => {
  if (pendingKeyAction.value === 'favorite') return 'rgb(234,179,8)'
  if (pendingKeyAction.value === 'delete') return 'rgb(239,68,68)'
  if (pendingKeyAction.value === 'damage') return 'rgb(168,85,247)'
  return 'transparent'
})
const keyBorderStyle = computed(() => {
  if (pendingKeyAction.value === 'favorite') {
    return {
      borderColor: keyActionColor.value,
      boxShadow: `inset 0 0 0 3px ${keyActionColor.value}`,
    }
  }
  if (pendingKeyAction.value === 'delete') {
    return {
      borderColor: keyActionColor.value,
      boxShadow: `inset 0 0 0 3px ${keyActionColor.value}`,
    }
  }
  if (pendingKeyAction.value === 'damage') {
    return {
      borderColor: keyActionColor.value,
      boxShadow: `inset 0 0 0 3px ${keyActionColor.value}`,
    }
  }
  return {}
})
const keyIconStyle = computed(() => ({
  color: keyActionColor.value,
  width: 'min(calc(100vw - 2rem), calc(100vh - 7rem))',
  height: 'min(calc(100vw - 2rem), calc(100vh - 7rem))',
  filter: `drop-shadow(0 0 18px ${keyActionColor.value})`,
}))

function getVideoPosterUrl(item: MediaItem): string | null {
  if (item.media_type !== 'video') return null
  if (thumbMode.value === 'grid' && item.preview_path) return getPreviewUrl(item.id)
  if (item.thumbnail_path) return getThumbnailUrl(item.id)
  if (item.preview_path) return getPreviewUrl(item.id)
  return null
}

function getPassiveMediaUrl(item: MediaItem | null): string | null {
  if (!item) return null
  if (item.media_type === 'image') return getStreamUrl(item.id)
  return getVideoPosterUrl(item)
}

const prevDisplayUrl = computed(() => getPassiveMediaUrl(prevItem.value))
const nextDisplayUrl = computed(() => getPassiveMediaUrl(nextItem.value))
const currentVideoPosterUrl = computed(() => current.value ? getVideoPosterUrl(current.value) : null)
const shortcutGroups = [
  {
    title: '浏览',
    items: [
      { keys: 'S / ↓', label: '下一个媒体' },
      { keys: 'W / ↑', label: '上一个媒体' },
      { keys: 'Esc', label: '退出漫游' },
    ],
  },
  {
    title: '标记',
    items: [
      { keys: 'F', label: '收藏，松开后跳到下一个' },
      { keys: 'D', label: '删除，松开后跳到下一个' },
      { keys: 'G', label: '损坏，松开后跳到下一个' },
    ],
  },
  {
    title: '视频',
    items: [
      { keys: 'Space', label: '播放 / 暂停' },
      { keys: 'Q / ←', label: '快退 30 秒' },
      { keys: 'E / →', label: '快进 30 秒' },
      { keys: '1 / 2 / 3', label: '1 倍 / 2 倍 / 3 倍速' },
      { keys: 'C / M / 0', label: '静音开关' },
    ],
  },
]

interface PreloadEntry {
  image?: HTMLImageElement
  video?: HTMLVideoElement
  videoPreload?: 'metadata' | 'auto'
}

const preloadedMedia = new Map<string, PreloadEntry>()
let preloadVersion = 0

function ensurePreloadEntry(item: MediaItem): PreloadEntry {
  let entry = preloadedMedia.get(item.id)
  if (!entry) {
    entry = {}
    preloadedMedia.set(item.id, entry)
  }
  return entry
}

function preloadMediaItem(item: MediaItem, distance: number) {
  const entry = ensurePreloadEntry(item)
  const imageUrl = getPassiveMediaUrl(item)

  if (imageUrl && !entry.image) {
    entry.image = createPreloadImage(imageUrl)
  }

  if (item.media_type !== 'video') return

  const preload = distance <= VIDEO_AUTO_PRELOAD_DISTANCE ? 'auto' : 'metadata'
  if (entry.video) {
    updateDetachedVideoPreload(entry.video, preload)
    entry.videoPreload = preload
    return
  }

  entry.video = createDetachedVideoPreloader(getStreamUrl(item.id), preload)
  entry.videoPreload = preload
}

function releasePreloadEntry(entry: PreloadEntry) {
  releaseMediaElement(entry.video)
  releaseImageElement(entry.image)
}

function releasePreloadForId(id: string | null | undefined) {
  if (!id) return
  const entry = preloadedMedia.get(id)
  if (!entry) return

  releasePreloadEntry(entry)
  preloadedMedia.delete(id)
}

function clearPreloadCache() {
  preloadVersion++
  for (const entry of preloadedMedia.values()) releasePreloadEntry(entry)
  preloadedMedia.clear()
}

function prunePreloadCache(retainedIds: Set<string>) {
  for (const [id, entry] of preloadedMedia.entries()) {
    if (!retainedIds.has(id)) {
      releasePreloadEntry(entry)
      preloadedMedia.delete(id)
    }
  }
}

function schedulePreload() {
  const version = ++preloadVersion
  window.setTimeout(() => {
    if (version !== preloadVersion) return

    const retainedIds = new Set<string>()
    preloadWindowItems.value.forEach((item, index) => {
      retainedIds.add(item.id)
      preloadMediaItem(item, index + 1)
    })

    prunePreloadCache(retainedIds)
  }, 0)
}

function toggleByAction(action: MarkAction, itemId: string): Promise<MediaItem> {
  if (action === 'favorite') return toggleFavorite(itemId)
  if (action === 'delete') return toggleDelete(itemId)
  return toggleDamaged(itemId)
}

function actionFromKey(key: string): MarkAction | null {
  const normalized = key.toLowerCase()
  if (normalized === 'f') return 'favorite'
  if (normalized === 'd') return 'delete'
  if (normalized === 'g') return 'damage'
  return null
}

function applyAction(action: MarkAction, item: MediaItem) {
  lastAction.value = { itemId: item.id, action }
  toggleByAction(action, item.id).then(updated => {
    const idx = items.value.findIndex(i => i.id === updated.id)
    if (idx !== -1) items.value[idx] = updated
  }).catch(() => {})
}

function seekVideo(deltaSeconds: number) {
  if (!videoEl.value) return
  const duration = Number.isFinite(videoEl.value.duration) ? videoEl.value.duration : Infinity
  const nextTime = Math.max(0, Math.min(duration, videoEl.value.currentTime + deltaSeconds))
  videoEl.value.currentTime = nextTime
}

function setPlaybackRate(rate: number) {
  playbackRate.value = rate
  if (videoEl.value) videoEl.value.playbackRate = rate
}

function toggleMute() {
  if (!videoEl.value) return
  videoEl.value.muted = !videoEl.value.muted
  isMuted.value = videoEl.value.muted
}

async function markCurrent(action: MarkAction) {
  if (isLocked.value || !current.value) return
  isLocked.value = true
  applyAction(action, current.value)
  phase.value = 'dragging'
  offsetX.value = 0
  offsetY.value = 0
  currentIndex.value++
  await new Promise(r => requestAnimationFrame(r))
  phase.value = 'idle'
  isLocked.value = false
}

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
      toggleByAction(action, itemId).then(updated => {
        const idx = items.value.findIndex(i => i.id === updated.id)
        if (idx !== -1) items.value[idx] = updated
      }).catch(() => {})
    }
    offsetY.value = vh
  } else if (direction === 'right' || direction === 'left') {
    // Fire action immediately, don't await
    if (current.value) applyAction(direction === 'right' ? 'favorite' : 'delete', current.value)
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
    let nextItems: MediaItem[] = []
    if (browseMode.value === 'random') {
      const res = await fetchRandom(
        LOAD_BATCH_SIZE, [...loadedIds.value], mediaType.value,
        hideMarked.value ? false : null,
        hideMarked.value ? false : null,
        hideMarked.value ? false : null,
      )
      nextItems = res.items
      if (res.items.length < LOAD_BATCH_SIZE) hasMore.value = false
    } else if (browseMode.value === 'folder') {
      nextItems = await loadFolderModeItems()
    } else {
      const params: Parameters<typeof fetchFeed>[0] = {
        page: orderedPage.value,
        page_size: LOAD_BATCH_SIZE,
        ...(mediaType.value && { media_type: mediaType.value }),
        ...(hideMarked.value && { is_favorited: false, is_deleted: false, is_damaged: false }),
        sort: 'size_desc',
      }
      const res = await fetchFeed(params)
      nextItems = res.items
      hasMore.value = res.has_next
      orderedPage.value++
    }

    for (const item of nextItems) {
      if (loadedIds.value.has(item.id)) continue
      loadedIds.value.add(item.id)
      items.value.push(item)
    }
    schedulePreload()
  } finally {
    loading.value = false
  }
}

function feedFilterParams(): Pick<Parameters<typeof fetchFeed>[0], 'media_type' | 'is_favorited' | 'is_deleted' | 'is_damaged'> {
  return {
    ...(mediaType.value && { media_type: mediaType.value }),
    ...(hideMarked.value && { is_favorited: false, is_deleted: false, is_damaged: false }),
  }
}

async function discoverNextFolder(): Promise<boolean> {
  while (true) {
    const res = await fetchFeed({
      ...feedFilterParams(),
      page: 1,
      page_size: 1,
      sort: 'file_path_asc',
      ...(folderAfter.value && { folder_after: folderAfter.value }),
    })
    const nextFolder = res.items[0]?.folder

    if (!nextFolder) {
      if (!folderWrapped.value && folderStart.value) {
        folderWrapped.value = true
        folderAfter.value = null
        continue
      }
      hasMore.value = false
      return false
    }

    if (folderWrapped.value && folderStart.value && nextFolder >= folderStart.value) {
      hasMore.value = false
      return false
    }

    folderAnchor.value = nextFolder
    orderedPage.value = 1
    return true
  }
}

async function loadFolderModeItems(): Promise<MediaItem[]> {
  while (true) {
    if (!folderAnchor.value) {
      folderAnchor.value = current.value?.folder || items.value[0]?.folder || folderStart.value
      if (folderAnchor.value && !folderStart.value) folderStart.value = folderAnchor.value
    }

    if (!folderAnchor.value && !(await discoverNextFolder())) return []

    const activeFolder = folderAnchor.value
    if (!activeFolder) {
      hasMore.value = false
      return []
    }

    const res = await fetchFeed({
      ...feedFilterParams(),
      page: orderedPage.value,
      page_size: LOAD_BATCH_SIZE,
      folder: activeFolder,
      folder_exact: true,
      sort: 'file_path_asc',
    })
    orderedPage.value++

    if (!res.has_next) {
      folderAfter.value = activeFolder
      folderAnchor.value = null
      orderedPage.value = 1
      hasMore.value = true
    } else {
      hasMore.value = true
    }

    if (res.items.length > 0) return res.items
  }
}

function resetRoamingItems() {
  releaseMediaElement(videoEl.value)
  clearPreloadCache()
  items.value = []
  loadedIds.value = new Set()
  currentIndex.value = 0
  hasMore.value = true
  orderedPage.value = 1
  folderAfter.value = null
  folderWrapped.value = false
  folderStart.value = browseMode.value === 'folder' ? (folderAnchor.value || current.value?.folder || null) : null
  lastAction.value = null
  pendingKeyAction.value = null
  videoPaused.value = true
}

function toggleHideMarked() {
  hideMarked.value = !hideMarked.value
  resetRoamingItems()
  loadMore()
}

function setMediaType(type: MediaType | null) {
  mediaType.value = type
  resetRoamingItems()
  loadMore()
}

function cycleBrowseMode() {
  const currentModeIndex = browseModes.findIndex(item => item.mode === browseMode.value)
  const nextMode = browseModes[(currentModeIndex + 1) % browseModes.length].mode
  const anchor = current.value?.folder || folderAnchor.value
  browseMode.value = nextMode
  folderAnchor.value = nextMode === 'folder' ? anchor : null
  resetRoamingItems()
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
watch(current, async (item, previousItem) => {
  if (previousItem?.media_type === 'video') {
    releaseMediaElement(videoEl.value)
  }

  await nextTick()

  if (!item || current.value?.id !== item.id) {
    videoPaused.value = true
    schedulePreload()
    return
  }

  if (item.media_type === 'video' && videoEl.value) {
    releasePreloadForId(item.id)
    const wantMuted = isMuted.value
    videoEl.value.muted = true
    videoEl.value.volume = userVolume.value || 1
    videoEl.value.playbackRate = playbackRate.value
    if (thumbMode.value === 'grid') {
      videoEl.value.pause()
      videoPaused.value = true
    } else {
      setTimeout(() => {
        if (videoEl.value && !videoEl.value.paused) videoPaused.value = false
      }, 500)
      try {
        await videoEl.value.play()
        videoEl.value.muted = wantMuted
        videoPaused.value = false
      } catch { /* autoplay blocked */ }
    }
  } else {
    videoPaused.value = true
  }
  if (currentIndex.value >= items.value.length - 8) loadMore()
  schedulePreload()
})

function onVolumeChange() {
  if (!videoEl.value) return
  isMuted.value = videoEl.value.muted
  userVolume.value = videoEl.value.volume
}

// Click left/right blank area to delete/favorite (desktop only)
function handleClick(e: MouseEvent) {
  if ('ontouchstart' in window) return
  if (isLocked.value || !current.value) return
  const target = e.target as HTMLElement
  if (target.tagName === 'IMG' || target.tagName === 'VIDEO') return
  if (e.clientX < window.innerWidth / 2) handleSwipe('left')   // delete
  else handleSwipe('right')                                      // favorite
}

// Keyboard
function onKeydown(e: KeyboardEvent) {
  if (showHelp.value) {
    if (e.key === 'Escape') showHelp.value = false
    return
  }

  const action = actionFromKey(e.key)
  if (action) {
    e.preventDefault()
    if (!e.repeat && !pendingKeyAction.value && !isLocked.value && current.value) {
      pendingKeyAction.value = action
    }
  } else if (e.key === ' ') {
    e.preventDefault()
    if (videoEl.value) videoEl.value.paused ? videoEl.value.play() : videoEl.value.pause()
  } else if (e.key === 'Escape') emit('close')
  else if (e.key === 'ArrowDown') handleSwipe('up')
  else if (e.key === 'ArrowUp') handleSwipe('down')
  else if (e.key.toLowerCase() === 's') handleSwipe('up')
  else if (e.key.toLowerCase() === 'w') handleSwipe('down')
  else if (e.key === 'ArrowLeft' || e.key.toLowerCase() === 'q') seekVideo(-30)
  else if (e.key === 'ArrowRight' || e.key.toLowerCase() === 'e') seekVideo(30)
  else if (e.key === '1') setPlaybackRate(1)
  else if (e.key === '2') setPlaybackRate(2)
  else if (e.key === '3') setPlaybackRate(3)
  else if (e.key === 'm' || e.key.toLowerCase() === 'c' || e.key === '0') toggleMute()
}

function onKeyup(e: KeyboardEvent) {
  const action = actionFromKey(e.key)
  if (!action || pendingKeyAction.value !== action) return
  e.preventDefault()
  pendingKeyAction.value = null
  markCurrent(action)
}

function clearPendingKeyAction() {
  pendingKeyAction.value = null
}

onMounted(() => {
  attach()
  loadMore()
  window.addEventListener('keydown', onKeydown)
  window.addEventListener('keyup', onKeyup)
  window.addEventListener('blur', clearPendingKeyAction)
})

onUnmounted(() => {
  detach()
  releaseMediaElement(videoEl.value)
  clearPreloadCache()
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('keyup', onKeyup)
  window.removeEventListener('blur', clearPendingKeyAction)
})
</script>

<template>
  <div
    class="fixed inset-0 z-50 text-white overflow-hidden select-none"
    :style="{
      touchAction: 'none',
      background: currentBackground,
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
          :title="hideMarked ? '显示全部' : '隐藏已收藏/已删除/已损坏'"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path v-if="hideMarked" stroke-linecap="round" stroke-linejoin="round" d="M3 3l18 18M10.5 10.5a3 3 0 004.243 4.243m0 0l1.536-1.536M6.75 6.75a7.5 7.5 0 009.743 9.743"/>
            <path v-if="hideMarked" stroke-linecap="round" d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            <path v-if="!hideMarked" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z"/>
            <path v-if="!hideMarked" d="M2.458 12C3.732 7.943 7.523 5 12 5c4.478 0 8.268 2.943 9.542 7-1.274 4.057-5.064 7-9.542 7-4.477 0-8.268-2.943-9.542-7z"/>
          </svg>
        </button>
        <button
          @click="showHelp = true"
          class="w-8 h-8 flex items-center justify-center rounded-full bg-white/10 text-white/60 hover:text-white transition-colors"
          title="快捷键说明"
        >
          <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" />
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.5 9a2.7 2.7 0 115 1.6c-.9.7-1.7 1.2-2 2.4" />
            <path stroke-linecap="round" d="M12 17h.01" />
          </svg>
        </button>
      </div>
      <TypeFilter :current="mediaType" @change="setMediaType" />
      <div class="flex items-center justify-end gap-2">
        <button
          @click="cycleBrowseMode"
          class="h-8 px-2.5 flex items-center gap-1.5 rounded-full bg-white/10 text-xs text-white/70 hover:text-white transition-colors"
          :title="currentBrowseMode.title"
        >
          <svg
            v-if="browseMode === 'random'"
            class="w-4 h-4 shrink-0"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M16 3h5v5M4 20l6.5-6.5M21 3l-7.5 7.5" />
            <path stroke-linecap="round" stroke-linejoin="round" d="M21 16v5h-5M4 4l17 17" />
          </svg>
          <svg
            v-else-if="browseMode === 'folder'"
            class="w-4 h-4 shrink-0"
            fill="currentColor"
            viewBox="0 0 24 24"
          >
            <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z" />
          </svg>
          <svg
            v-else
            class="w-4 h-4 shrink-0"
            fill="none"
            stroke="currentColor"
            stroke-width="2"
            viewBox="0 0 24 24"
          >
            <path stroke-linecap="round" stroke-linejoin="round" d="M4 7h12M4 12h8M4 17h4M18 6v12M15 15l3 3 3-3" />
          </svg>
          <span class="hidden sm:inline">{{ currentBrowseMode.label }}</span>
        </button>
        <span class="text-xs text-white/50 tabular-nums w-12 text-right">{{ currentIndex + 1 }}</span>
      </div>
    </header>

    <div
      v-if="showHelp"
      class="absolute inset-0 z-40 flex items-center justify-center bg-black/70 px-4"
      @click.self="showHelp = false"
    >
      <div class="w-full max-w-lg rounded-lg border border-white/15 bg-gray-950 text-white shadow-2xl">
        <div class="flex items-center justify-between border-b border-white/10 px-4 py-3">
          <h2 class="text-base font-semibold">漫游快捷键</h2>
          <button
            @click="showHelp = false"
            class="w-8 h-8 flex items-center justify-center rounded-full text-white/60 hover:bg-white/10 hover:text-white transition-colors"
            title="关闭"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
          </button>
        </div>
        <div class="max-h-[70vh] overflow-y-auto px-4 py-3">
          <section v-for="group in shortcutGroups" :key="group.title" class="py-2">
            <h3 class="mb-2 text-xs font-semibold text-white/45">{{ group.title }}</h3>
            <div class="divide-y divide-white/10">
              <div
                v-for="item in group.items"
                :key="item.keys"
                class="flex items-center justify-between gap-4 py-2 text-sm"
              >
                <kbd class="shrink-0 rounded border border-white/20 bg-white/10 px-2 py-1 font-mono text-xs text-white/80">{{ item.keys }}</kbd>
                <span class="text-right text-white/75">{{ item.label }}</span>
              </div>
            </div>
          </section>
        </div>
      </div>
    </div>

    <!-- Card stack -->
    <div ref="containerRef" class="absolute inset-0" @click="handleClick">
      <!-- Previous item (above viewport) -->
      <div
        v-if="prevItem"
        :key="`prev-${prevItem.id}`"
        class="absolute inset-0 flex items-center justify-center p-4 pt-16 pb-8"
        :style="{
          transform: `translateY(calc(-100% + ${offsetY}px))`,
          transition: hasTransition ? 'transform 200ms ease-out' : 'none',
        }"
      >
        <img
          v-if="prevDisplayUrl"
          :src="prevDisplayUrl"
          class="max-w-full max-h-full object-contain rounded-lg"
        />
        <div
          v-else
          class="flex aspect-video w-full max-w-4xl items-center justify-center rounded-lg bg-black"
        >
          <svg class="w-16 h-16 text-white/55" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
        </div>
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
          :poster="currentVideoPosterUrl || undefined"
          preload="auto"
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
          v-if="current.media_type === 'video' && thumbMode === 'grid' && videoPaused && currentVideoPosterUrl"
          class="absolute inset-0 flex items-center justify-center cursor-pointer"
          @click.stop="videoEl && videoEl.play()"
        >
          <img
            :src="currentVideoPosterUrl"
            class="max-w-full max-h-full object-contain rounded-lg"
          />
          <div class="absolute inset-0 flex items-center justify-center pointer-events-none">
            <div class="w-20 h-20 rounded-full bg-black/40 flex items-center justify-center">
              <svg class="w-10 h-10 text-white ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
            </div>
          </div>
        </div>
        <div
          v-else-if="current.media_type === 'video' && videoPaused"
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
        :key="`next-${nextItem.id}`"
        class="absolute inset-0 flex items-center justify-center p-4 pt-16 pb-8"
        :style="{
          transform: `translateY(calc(100% + ${offsetY}px))`,
          transition: hasTransition ? 'transform 200ms ease-out' : 'none',
        }"
      >
        <img
          v-if="nextDisplayUrl"
          :src="nextDisplayUrl"
          class="max-w-full max-h-full object-contain rounded-lg"
        />
        <div
          v-else
          class="flex aspect-video w-full max-w-4xl items-center justify-center rounded-lg bg-black"
        >
          <svg class="w-16 h-16 text-white/55" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
        </div>
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

    <div
      v-if="pendingKeyAction"
      class="absolute inset-0 z-20 pointer-events-none flex items-center justify-center border-[12px] p-4 pt-16 pb-8"
      :style="keyBorderStyle"
    >
      <svg
        v-if="pendingKeyAction === 'delete'"
        :style="keyIconStyle"
        class="max-w-full max-h-full"
        fill="none"
        stroke="currentColor"
        stroke-linecap="round"
        stroke-width="5"
        viewBox="0 0 100 100"
      >
        <path d="M22 22L78 78M78 22L22 78" />
      </svg>
      <svg
        v-else-if="pendingKeyAction === 'favorite'"
        :style="keyIconStyle"
        class="max-w-full max-h-full"
        fill="none"
        stroke="currentColor"
        stroke-linejoin="round"
        stroke-width="4"
        viewBox="0 0 100 100"
      >
        <path d="M50 12l11.4 23.1 25.5 3.7-18.5 18 4.4 25.4L50 70.2 27.2 82.2l4.4-25.4-18.5-18 25.5-3.7L50 12z" />
      </svg>
      <svg
        v-else
        :style="keyIconStyle"
        class="max-w-full max-h-full"
        fill="none"
        stroke="currentColor"
        stroke-linecap="round"
        stroke-linejoin="round"
        stroke-width="4"
        viewBox="0 0 100 100"
      >
        <path d="M16 22a6 6 0 016-6h56a6 6 0 016 6v56a6 6 0 01-6 6H22a6 6 0 01-6-6V22z" />
        <path d="M23 72l18-21 14 15 10-13 12 19" />
        <path d="M54 17l-9 18 12 7-11 17 14 8-10 16" />
        <circle cx="35" cy="34" r="6" />
      </svg>
    </div>

    <!-- Bottom info + progress — desktop: bottom 25vh for large seek target -->
    <div
      v-if="current"
      class="absolute bottom-0 inset-x-0 z-10 px-4 pb-4 md:h-[25vh] md:flex md:flex-col md:justify-end"
      @pointerdown.stop @click.stop @touchstart.stop
    >
      <VideoProgress v-if="current.media_type === 'video'" :video="videoEl" :tall-bar="isDesktop" />
      <p class="text-sm text-white/60 text-center truncate">{{ current.file_path.split(/[/\\]/).pop() }}</p>
    </div>
  </div>
</template>
