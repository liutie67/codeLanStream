<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import type { MediaItem, MediaType } from '../api/types'
import { fetchRandom, toggleFavorite, batchUpdate } from '../api/client'
import { useColumnLayout } from '../composables/useColumnLayout'
import TypeFilter from './TypeFilter.vue'
import MediaImage from './MediaImage.vue'
import VideoPlayer from './VideoPlayer.vue'

const emit = defineEmits<{ close: [] }>()
const props = defineProps<{ folder?: string }>()


const items = ref<MediaItem[]>([])
const loadedIds = ref<Set<string>>(new Set())
const mediaType = ref<MediaType | null>(null)
const loading = ref(false)
const error = ref('')
const hasMore = ref(true)
const favoriteIds = ref<Set<string>>(new Set())
const scrolledPastIds = ref<Set<string>>(new Set())
const previewItem = ref<MediaItem | null>(null)
const colMode = ref(5)
const scrollRef = ref<HTMLElement>()
const cardRefs = new Map<string, HTMLElement>()

const colCount = computed(() => colMode.value)
const { columns } = useColumnLayout(items, colCount)
const columnRef = ref<HTMLElement>()
let seenObserver: IntersectionObserver | null = null
let scrollObserver: IntersectionObserver | null = null

async function loadMore() {
  if (loading.value || !hasMore.value) return
  loading.value = true
  error.value = ''
  try {
    const res = await fetchRandom(50, [...loadedIds.value], mediaType.value, false, false, null, props.folder)
    for (const item of res.items) loadedIds.value.add(item.id)
    items.value.push(...res.items)
    if (res.items.length < 50) hasMore.value = false
    pruneAbove()
  } catch (failure) {
    error.value = failure instanceof Error ? failure.message : '媒体读取失败'
  } finally {
    loading.value = false
  }
}

function setMediaType(type: MediaType | null) {
  mediaType.value = type
  items.value = []
  loadedIds.value = new Set()
  favoriteIds.value.clear()
  scrolledPastIds.value.clear()
  hasMore.value = true
  loadMore()
}

function cycleColMode() {
  const modes = [3, 5, 6]
  colMode.value = modes[(modes.indexOf(colMode.value) + 1) % 3]
}

function cardBorderClass(item: MediaItem) {
  if (favoriteIds.value.has(item.id)) return 'ring-2 ring-yellow-400'
  if (scrolledPastIds.value.has(item.id)) return 'ring-2 ring-red-500'
  return ''
}

function onCardClick(e: MouseEvent, item: MediaItem) {
  const target = e.currentTarget as HTMLElement
  const imgEl = target.querySelector('img, video') as HTMLElement | null
  const rect = (imgEl || target).getBoundingClientRect()
  const y = e.clientY - rect.top
  if (y < rect.height / 2) {
    toggleFav(item)
  } else {
    previewItem.value = item
  }
}

async function toggleFav(item: MediaItem) {
  await toggleFavorite(item.id)
  if (favoriteIds.value.has(item.id)) {
    favoriteIds.value.delete(item.id)
  } else {
    favoriteIds.value.add(item.id)
  }
  const idx = items.value.findIndex(i => i.id === item.id)
  if (idx !== -1) items.value[idx] = { ...items.value[idx], is_favorited: !items.value[idx].is_favorited }
}

function removeUnavailable(id: string) {
  items.value = items.value.filter(item => item.id !== id)
  favoriteIds.value.delete(id)
  scrolledPastIds.value.delete(id)
  if (previewItem.value?.id === id) closePreview()
}

function closePreview() {
    previewItem.value = null
}

function setupSeenObserver() {
  seenObserver?.disconnect()
  seenObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting) {
        const el = entry.target as HTMLElement
        const id = el.dataset.id
        if (id) scrollObserver?.observe(el)
      }
    }
  }, { root: scrollRef.value, threshold: 0 })
}

function setupScrollObserver() {
  scrollObserver?.disconnect()
  scrollObserver = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      const id = (entry.target as HTMLElement).dataset.id
      if (id && entry.isIntersecting) scrolledPastIds.value.add(id)
    }
  }, { root: scrollRef.value, rootMargin: '0px 0px -100% 0px', threshold: 0 })
}

function observeCard(el: HTMLElement, id: string) {
  cardRefs.set(id, el)
  seenObserver?.observe(el)
}

function onScroll() {
  if (error.value) return
  if (!scrollRef.value || loading.value || !hasMore.value || !columnRef.value) return
  const scrollBottom = scrollRef.value.getBoundingClientRect().bottom
  const colEls = columnRef.value.children
  let minBottom = Infinity
  for (const col of colEls) {
    const bottom = (col as HTMLElement).getBoundingClientRect().bottom
    if (bottom < minBottom) minBottom = bottom
  }
  if (minBottom < scrollBottom + 600) loadMore()
}

function pruneAbove() {
  if (!scrollRef.value) return
  const containerTop = scrollRef.value.getBoundingClientRect().top
  const threshold = scrollRef.value.clientHeight * 3

  const toRemoveIds: string[] = []
  for (const item of items.value) {
    const el = cardRefs.get(item.id)
    if (!el) continue
    const rect = el.getBoundingClientRect()
    if (rect.bottom < containerTop - threshold) {
      toRemoveIds.push(item.id)
    }
  }

  if (toRemoveIds.length === 0) return

  const removeSet = new Set(toRemoveIds)
  for (const id of removeSet) {
    const el = cardRefs.get(id)
    if (el) {
      seenObserver?.unobserve(el)
      scrollObserver?.unobserve(el)
    }
    cardRefs.delete(id)
  }

  items.value = items.value.filter(item => !removeSet.has(item.id))
}

async function exitTurbo() {
  const toDelete = [...scrolledPastIds.value].filter(id => !favoriteIds.value.has(id))

  if (toDelete.length === 0) { emit('close'); return }

  if (!confirm(`将标记 ${toDelete.length} 个未收藏媒体为删除`)) return

  await batchUpdate(toDelete, 'delete')
  emit('close')
}

onMounted(() => {
  setupSeenObserver()
  setupScrollObserver()
  loadMore()
})

onUnmounted(() => {
  seenObserver?.disconnect()
  scrollObserver?.disconnect()
})
</script>

<template>
  <div class="fixed inset-0 z-50 bg-gray-700/80 backdrop-blur text-white overflow-hidden flex flex-col">
    <!-- Top bar -->
    <header class="shrink-0 flex items-center justify-between px-4 py-3 bg-black/30">
      <div class="flex items-center gap-3">
        <button @click="emit('close')" class="w-8 h-8 flex items-center justify-center rounded-full bg-white/10 text-white/70 hover:text-white transition-colors">
          <svg class="w-5 h-5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M6 18L18 6M6 6l12 12"/></svg>
        </button>
        <span class="text-sm font-medium">极速模式</span>
        <TypeFilter :current="mediaType" @change="setMediaType" />
      </div>
      <div class="flex items-center gap-3">
        <button
          @click="cycleColMode"
          class="h-8 w-8 md:w-auto md:px-3 flex items-center justify-center gap-1 rounded-full border border-white/10 bg-white/10 text-xs font-medium text-white/75 shadow-sm transition-colors hover:text-white shrink-0"
          :title="`当前: ${colMode} 列，点击切换列数`"
          aria-label="切换列数"
        >
          <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <rect x="4" y="5" width="4" height="14" rx="1" />
            <rect x="10" y="5" width="4" height="14" rx="1" />
            <rect x="16" y="5" width="4" height="14" rx="1" />
          </svg>
          <span class="hidden md:inline">{{ colMode }} 列</span>
        </button>
        <button
          @click="exitTurbo"
          class="px-4 py-1.5 rounded-lg text-sm bg-red-600 hover:bg-red-500 transition-colors font-medium"
        >
          退出极速模式
        </button>
      </div>
    </header>

    <!-- Scrollable area -->
    <div ref="scrollRef" class="flex-1 overflow-y-auto px-4 py-4" @scroll="onScroll">
      <div ref="columnRef" class="flex items-start gap-3">
        <div v-for="(col, ci) in columns" :key="ci" class="flex-1 flex flex-col gap-3">
          <div
            v-for="item in col"
            :key="item.id"
            :data-id="item.id"
            :ref="(el: any) => el && observeCard(el as HTMLElement, item.id)"
            class="rounded-lg overflow-hidden cursor-pointer transition-shadow"
            :class="cardBorderClass(item)"
            @click="onCardClick($event, item)"
          >
            <div class="relative">
              <MediaImage :item="item" @unavailable="removeUnavailable" />
              <div v-if="item.media_type === 'video'" class="absolute inset-0 flex items-center justify-center bg-black/20 pointer-events-none">
                <svg class="w-8 h-8 text-white/70" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
              </div>
            </div>
          </div>
        </div>
      </div>

      <p v-if="error" class="py-4 text-center text-amber-400" role="alert">{{ error }} <button @click="loadMore" class="ml-3 text-blue-400">重试</button></p>
      <div v-if="loading" class="py-8 text-center text-white/50">
        <span class="inline-block animate-spin mr-2">&#9696;</span> 加载中...
      </div>
      <p v-else-if="!hasMore && items.length" class="py-8 text-center text-white/30 text-sm">已加载全部</p>
    </div>

    <Teleport to="body">
      <VideoPlayer v-if="previewItem" :item="previewItem" @close="closePreview" @unavailable="removeUnavailable" />
    </Teleport>
  </div>
</template>
