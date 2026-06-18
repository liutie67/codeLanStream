<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import type { MediaItem } from '../api/types'
import { getPreviewUrl, getStreamUrl, getThumbnailUrl } from '../api/client'
import { useFeed } from '../composables/useFeed'
import { useColumnLayout } from '../composables/useColumnLayout'
import { useTheme } from '../composables/useTheme'
import { useThumbnailMode } from '../composables/useThumbnailMode'
import TypeFilter from '../components/TypeFilter.vue'
import MediaCard from '../components/MediaCard.vue'
import VideoPlayer from '../components/VideoPlayer.vue'
import FolderBrowser from '../components/FolderBrowser.vue'
import RoamingView from '../components/RoamingView.vue'
import TurboView from '../components/TurboView.vue'

type ColumnMode = 'auto' | '1' | '2'

const LOAD_AHEAD_PX = 2800
const PREFETCH_CONCURRENCY = 6
const PREFETCH_LOOKBACK = 16
const PREFETCH_MAX_ITEMS = 120
const PREFETCH_URL_CACHE_LIMIT = 360

const { items, loading, hasMore, total, mediaType, loadMore, refresh, setMediaType } = useFeed()
const { isDark, toggleTheme } = useTheme()
const { thumbMode, toggleMode } = useThumbnailMode()
const activeItem = ref<MediaItem | null>(null)
const showFolders = ref(false)
const showRoaming = ref(false)
const showTurbo = ref(false)
const colMode = ref<ColumnMode>('auto')

const colCount = computed(() => {
  if (colMode.value === '1') return 1
  if (colMode.value === '2') return 2
  return 4
})

const { columns, updateItem } = useColumnLayout(items, colCount)
const columnRef = ref<HTMLElement>()
const prefetchedUrls = new Set<string>()
const prefetchQueue: string[] = []
let prefetchActive = 0
let nextPrefetchIndex = 0
let stopped = false

const thumbModeTitle = computed(() => (
  thumbMode.value === 'grid' ? '当前: 预览，点击切换到首帧' : '当前: 首帧，点击切换到预览'
))

const colModeTitle = computed(() => {
  if (colMode.value === 'auto') return '当前: 自动列数，点击切换到单列'
  if (colMode.value === '1') return '当前: 单列，点击切换到双列'
  return '当前: 双列，点击切换到自动'
})

function cycleColMode() {
  const modes: ColumnMode[] = ['auto', '1', '2']
  const idx = modes.indexOf(colMode.value)
  colMode.value = modes[(idx + 1) % modes.length]
}

function onItemUpdated(updated: MediaItem) {
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
  updateItem(updated)
}

async function onScroll() {
  if (loading.value || !hasMore.value || !columnRef.value) return
  const colEls = columnRef.value.children
  let minBottom = Infinity
  for (const col of colEls) {
    const bottom = (col as HTMLElement).getBoundingClientRect().bottom
    if (bottom < minBottom) minBottom = bottom
  }
  if (minBottom < window.innerHeight + LOAD_AHEAD_PX) {
    await loadMore()
    requestAnimationFrame(onScroll)
  }
}

function getPreloadUrl(item: MediaItem): string | null {
  if (item.media_type === 'image') return getStreamUrl(item.id)
  if (thumbMode.value === 'grid' && item.preview_path) return getPreviewUrl(item.id)
  if (item.thumbnail_path) return getThumbnailUrl(item.id)
  return null
}

function rememberPrefetchedUrl(url: string) {
  prefetchedUrls.add(url)
  while (prefetchedUrls.size > PREFETCH_URL_CACHE_LIMIT) {
    const oldest = prefetchedUrls.values().next().value
    if (!oldest) break
    prefetchedUrls.delete(oldest)
  }
}

function enqueuePreload(url: string) {
  if (prefetchedUrls.has(url) || prefetchQueue.includes(url)) return
  rememberPrefetchedUrl(url)
  prefetchQueue.push(url)
  pumpPreloadQueue()
}

function pumpPreloadQueue() {
  if (stopped) return
  while (prefetchActive < PREFETCH_CONCURRENCY && prefetchQueue.length) {
    const url = prefetchQueue.shift()
    if (!url) return
    prefetchActive++
    const img = new Image()
    img.decoding = 'async'
    img.onload = img.onerror = () => {
      prefetchActive--
      pumpPreloadQueue()
    }
    img.src = url
  }
}

function prefetchAhead(reset = false) {
  if (reset) {
    prefetchQueue.length = 0
    nextPrefetchIndex = 0
  }

  const start = Math.max(0, nextPrefetchIndex - PREFETCH_LOOKBACK)
  const end = Math.min(items.value.length, nextPrefetchIndex + PREFETCH_MAX_ITEMS)
  for (const item of items.value.slice(start, end)) {
    const url = getPreloadUrl(item)
    if (url) enqueuePreload(url)
  }
  nextPrefetchIndex = Math.max(nextPrefetchIndex, end)
}

watch(
  () => items.value.length,
  (len, oldLen) => {
    if (len < (oldLen ?? 0)) {
      prefetchedUrls.clear()
      prefetchAhead(true)
      return
    }
    prefetchAhead()
  },
  { immediate: true },
)

watch(thumbMode, () => {
  prefetchedUrls.clear()
  prefetchAhead(true)
})

onMounted(() => {
  window.addEventListener('scroll', onScroll, { passive: true })
  onScroll()
})
onUnmounted(() => {
  stopped = true
  prefetchQueue.length = 0
  window.removeEventListener('scroll', onScroll)
})
</script>

<template>
  <div :class="['min-h-screen', isDark ? 'bg-gray-950 text-white' : 'bg-gray-50 text-gray-900']">
    <header :class="['sticky top-0 z-40 backdrop-blur border-b', isDark ? 'bg-gray-950/90 border-gray-800' : 'bg-white/90 border-gray-200']">
      <div class="px-4 lg:px-6 py-2 flex items-center justify-between gap-2">
        <div class="flex items-center gap-3">
          <h1 class="text-lg font-bold tracking-tight shrink-0">LanStream</h1>
          <RouterLink
            to="/manage"
            class="hidden md:inline text-xs text-gray-500 hover:text-gray-300 transition-colors"
          >
            管理
          </RouterLink>
        </div>
        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-500 tabular-nums">{{ total }}</span>
          <button
            @click="showFolders = true"
            :class="['w-7 h-7 flex items-center justify-center rounded-full transition-colors shrink-0', isDark ? 'bg-gray-800 text-yellow-400 hover:bg-gray-700' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']"
            title="浏览文件夹"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/>
            </svg>
          </button>
          <button
            @click="showRoaming = true"
            :class="['w-7 h-7 flex items-center justify-center rounded-full transition-colors shrink-0', isDark ? 'bg-gray-800 text-blue-400 hover:bg-gray-700' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']"
            title="漫游模式"
          >
            <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <path d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
            </svg>
          </button>
          <button
            v-if="!showTurbo"
            @click="showTurbo = true"
            class="hidden md:flex w-7 h-7 items-center justify-center rounded-full bg-gray-800 text-yellow-400 hover:bg-gray-700 transition-colors shrink-0"
            title="极速模式"
          >
            <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
            </svg>
          </button>
          <button
            @click="toggleTheme"
            :class="['w-7 h-7 flex items-center justify-center rounded-full transition-colors shrink-0', isDark ? 'bg-gray-800 text-yellow-400 hover:bg-gray-700' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']"
            :title="isDark ? '浅色模式' : '深色模式'"
          >
            <svg v-if="isDark" class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.22 4.22l1.42 1.42M18.36 18.36l1.42 1.42M1 12h2M21 12h2M4.22 19.78l1.42-1.42M18.36 5.64l1.42-1.42"/>
            </svg>
            <svg v-else class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
              <path d="M21.64 13a9 9 0 11-9-9 7 7 0 009 9z"/>
            </svg>
          </button>
          <button
            @click="toggleMode"
            :class="[
              'h-8 w-8 md:w-auto md:px-2.5 flex items-center justify-center gap-1 rounded-full border text-xs font-medium shadow-sm transition-colors shrink-0',
              thumbMode === 'grid'
                ? 'border-emerald-500 bg-emerald-600 text-white'
                : isDark ? 'border-gray-700 bg-gray-800 text-gray-300 hover:text-white' : 'border-gray-200 bg-white text-gray-600 hover:text-gray-900',
            ]"
            :title="thumbModeTitle"
            aria-label="切换预览模式"
          >
            <svg
              v-if="thumbMode === 'grid'"
              class="w-4 h-4 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <rect x="4" y="4" width="6" height="6" rx="1" />
              <rect x="14" y="4" width="6" height="6" rx="1" />
              <rect x="4" y="14" width="6" height="6" rx="1" />
              <rect x="14" y="14" width="6" height="6" rx="1" />
            </svg>
            <svg
              v-else
              class="w-4 h-4 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <rect x="4" y="5" width="16" height="14" rx="2" />
              <path d="M10 9l5 3-5 3V9z" fill="currentColor" stroke="none" />
            </svg>
            <span class="hidden md:inline">{{ thumbMode === 'grid' ? '预览' : '首帧' }}</span>
          </button>
          <button
            @click="cycleColMode"
            :class="[
              'h-8 w-8 md:w-auto md:px-2.5 flex items-center justify-center gap-1 rounded-full border text-xs font-medium shadow-sm transition-colors shrink-0',
              isDark ? 'border-gray-700 bg-gray-800 text-gray-300 hover:text-white' : 'border-gray-200 bg-white text-gray-600 hover:text-gray-900',
            ]"
            :title="colModeTitle"
            aria-label="切换列布局"
          >
            <svg
              v-if="colMode === 'auto'"
              class="w-4 h-4 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <rect x="4" y="4" width="7" height="7" rx="1" />
              <rect x="13" y="4" width="7" height="5" rx="1" />
              <rect x="4" y="13" width="7" height="7" rx="1" />
              <rect x="13" y="11" width="7" height="9" rx="1" />
            </svg>
            <svg
              v-else-if="colMode === '1'"
              class="w-4 h-4 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <rect x="7" y="4" width="10" height="16" rx="2" />
            </svg>
            <svg
              v-else
              class="w-4 h-4 shrink-0"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
              viewBox="0 0 24 24"
            >
              <rect x="4" y="4" width="7" height="16" rx="2" />
              <rect x="13" y="4" width="7" height="16" rx="2" />
            </svg>
            <span class="hidden md:inline">{{ colMode === 'auto' ? '自动' : colMode === '1' ? '单列' : '双列' }}</span>
          </button>
          <TypeFilter :current="mediaType" @change="setMediaType" />
        </div>
      </div>
    </header>

    <main class="px-4 lg:px-6 py-4">
      <div
        ref="columnRef"
        class="flex items-start gap-2"
        :style="colMode === '1' ? 'max-width: 720px; margin: 0 auto' : ''"
      >
        <div v-for="(col, ci) in columns" :key="ci" class="flex-1 flex flex-col gap-2">
          <MediaCard
            v-for="item in col"
            :key="item.id"
            :item="item"
            @click="activeItem = $event"
            @updated="onItemUpdated"
          />
        </div>
      </div>

      <div v-if="loading" class="py-8 text-center text-gray-400">
        <span class="inline-block animate-spin mr-2">&#9696;</span> 加载中...
      </div>
      <p v-else-if="!hasMore && items.length" class="py-8 text-center text-gray-500 text-sm">已加载全部</p>
    </main>

    <FolderBrowser
      v-if="showFolders"
      @close="showFolders = false"
      @play="activeItem = $event"
      @imported="refresh"
    />
    <RoamingView
      v-if="showRoaming"
      @close="showRoaming = false"
    />
    <TurboView
      v-if="showTurbo"
      @close="showTurbo = false"
    />
    <VideoPlayer
      v-if="activeItem"
      :item="activeItem"
      @close="activeItem = null"
    />
  </div>
</template>
