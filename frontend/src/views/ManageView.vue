<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import type { MediaItem } from '../api/types'
import { fetchFeed, getThumbnailUrl, getStreamUrl, purgeDeleted, exportFavorites, batchUpdate, toggleFavorite, toggleDelete } from '../api/client'
import { useTheme } from '../composables/useTheme'

type FilterMode = 'all' | 'favorited' | 'deleted'
type ThumbSize = 'small' | 'medium' | 'large'

const { isDark } = useTheme()

const items = ref<MediaItem[]>([])
const filter = ref<FilterMode>('all')
const selected = ref<Set<string>>(new Set())
const exportDir = ref('')
const message = ref('')
const loading = ref(false)
const hasMore = ref(true)
const page = ref(1)
const thumbSize = ref<ThumbSize>('small')
const previewItem = ref<MediaItem | null>(null)
const counts = ref({ all: 0, favorited: 0, deleted: 0 })
const sentinelRef = ref<HTMLElement>()
let observer: IntersectionObserver | null = null

const PAGE_SIZE = 300

const thumbClasses = computed(() => {
  switch (thumbSize.value) {
    case 'small': return 'w-16 h-12'
    case 'medium': return 'w-24 h-16'
    case 'large': return 'w-36 h-24'
  }
})

const thumbSizeLabel = computed(() => {
  switch (thumbSize.value) {
    case 'small': return '小'
    case 'medium': return '中'
    case 'large': return '大'
  }
})

function cycleThumbSize() {
  const sizes: ThumbSize[] = ['small', 'medium', 'large']
  thumbSize.value = sizes[(sizes.indexOf(thumbSize.value) + 1) % 3]
}

async function loadCounts() {
  const [all, fav, del] = await Promise.all([
    fetchFeed({ page: 1, page_size: 1 }),
    fetchFeed({ page: 1, page_size: 1, is_favorited: true }),
    fetchFeed({ page: 1, page_size: 1, is_deleted: true }),
  ])
  counts.value = { all: all.total, favorited: fav.total, deleted: del.total }
}

async function loadItems(reset = false) {
  if (loading.value) return
  if (!reset && !hasMore.value) return

  loading.value = true
  if (reset) {
    page.value = 1
    items.value = []
    hasMore.value = true
  }

  try {
    const params: Record<string, unknown> = { page: page.value, page_size: PAGE_SIZE }
    if (filter.value === 'favorited') params.is_favorited = true
    if (filter.value === 'deleted') params.is_deleted = true

    const res = await fetchFeed(params as Parameters<typeof fetchFeed>[0])
    if (reset) items.value = res.items
    else items.value.push(...res.items)
    hasMore.value = res.has_next
    page.value++
  } finally {
    loading.value = false
  }
}

async function setFilter(f: FilterMode) {
  if (filter.value === f) return
  filter.value = f
  selected.value.clear()
  await loadItems(true)
}

function toggleSelect(id: string) {
  if (selected.value.has(id)) selected.value.delete(id)
  else selected.value.add(id)
}

function selectAll() {
  if (selected.value.size === items.value.length && items.value.length > 0) {
    selected.value.clear()
  } else {
    selected.value = new Set(items.value.map(i => i.id))
  }
}

async function doBatch(action: string) {
  if (selected.value.size === 0) return
  await batchUpdate([...selected.value], action)
  message.value = `已更新 ${selected.value.size} 项`
  selected.value.clear()
  await Promise.all([loadItems(true), loadCounts()])
  setTimeout(() => message.value = '', 3000)
}

async function doPurge() {
  if (!counts.value.deleted || !confirm(`确定物理删除 ${counts.value.deleted} 个文件？此操作不可撤销。`)) return
  const res = await purgeDeleted()
  message.value = `已删除 ${res.deleted_count} 个文件`
  await Promise.all([loadItems(true), loadCounts()])
  setTimeout(() => message.value = '', 3000)
}

async function doExport() {
  if (!exportDir.value.trim()) { message.value = '请输入导出目录路径'; setTimeout(() => message.value = '', 3000); return }
  const res = await exportFavorites(exportDir.value.trim())
  message.value = `已导出 ${res.exported_count} 个文件到 ${exportDir.value}`
  setTimeout(() => message.value = '', 5000)
}

async function doToggleFavorite(id: string) {
  const updated = await toggleFavorite(id)
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
  loadCounts()
  if (filter.value === 'favorited') await loadItems(true)
}

async function doToggleDelete(id: string) {
  const updated = await toggleDelete(id)
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
  loadCounts()
  if (filter.value === 'deleted') await loadItems(true)
}

function openPreview(item: MediaItem) {
  previewItem.value = item
}

function closePreview() {
  previewItem.value = null
}

function onPreviewKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closePreview()
}

watch(previewItem, (val) => {
  if (val) window.addEventListener('keydown', onPreviewKeydown)
  else window.removeEventListener('keydown', onPreviewKeydown)
})

// Infinite scroll
function setupObserver() {
  observer?.disconnect()
  observer = new IntersectionObserver((entries) => {
    if (entries[0]?.isIntersecting && hasMore.value && !loading.value) {
      loadItems()
    }
  }, { rootMargin: '200px' })
  if (sentinelRef.value) observer.observe(sentinelRef.value)
}

watch(sentinelRef, () => {
  if (sentinelRef.value) setupObserver()
})

onMounted(async () => {
  await Promise.all([loadItems(true), loadCounts()])
})

onUnmounted(() => {
  observer?.disconnect()
  window.removeEventListener('keydown', onPreviewKeydown)
})
</script>

<template>
  <div :class="['min-h-screen hidden md:block', isDark ? 'bg-gray-950 text-white' : 'bg-gray-50 text-gray-900']">
    <!-- 移动端提示 -->
    <div class="block md:hidden p-8 text-center text-gray-500">
      管理功能仅支持桌面端
    </div>

    <!-- 桌面端内容 -->
    <header :class="['sticky top-0 z-40 backdrop-blur border-b', isDark ? 'bg-gray-950/90 border-gray-800' : 'bg-white/90 border-gray-200']">
      <div class="px-4 lg:px-6 py-3 flex items-center justify-between">
        <div class="flex items-center gap-4">
          <RouterLink to="/" class="text-lg font-bold tracking-tight hover:text-gray-300 transition-colors">LanStream</RouterLink>
          <span class="text-sm text-gray-500">管理</span>
        </div>
        <RouterLink to="/" class="text-sm text-blue-400 hover:text-blue-300">返回浏览</RouterLink>
      </div>
    </header>

    <main class="px-4 lg:px-6 py-6">
      <!-- 消息提示 -->
      <div v-if="message" :class="['mb-4 px-4 py-2 rounded-lg text-sm text-center', isDark ? 'bg-gray-800' : 'bg-gray-200']">{{ message }}</div>

      <!-- 操作栏 -->
      <div class="flex flex-wrap items-center gap-3 mb-6">
        <button
          @click="doPurge"
          class="px-4 py-2 bg-red-600/20 text-red-400 border border-red-600/30 rounded-lg text-sm hover:bg-red-600/30 transition-colors"
        >
          一键清理已删除 ({{ counts.deleted }})
        </button>
        <div class="flex items-center gap-2">
          <input
            v-model="exportDir"
            placeholder="导出收藏到目录..."
            :class="['px-3 py-2 border rounded-lg text-sm placeholder-gray-500 w-64', isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300 text-gray-900']"
          />
          <button
            @click="doExport"
            class="px-4 py-2 bg-pink-600/20 text-pink-400 border border-pink-600/30 rounded-lg text-sm hover:bg-pink-600/30 transition-colors"
          >
            导出收藏 ({{ counts.favorited }})
          </button>
        </div>
      </div>

      <!-- 筛选 + 批量操作 + 缩略图尺寸 -->
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2">
          <button
            v-for="f in (['all', 'favorited', 'deleted'] as FilterMode[])"
            :key="f"
            @click="setFilter(f)"
            :class="[
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              filter === f ? 'bg-blue-600 text-white' : isDark ? 'bg-gray-800 text-gray-400 hover:text-gray-200' : 'bg-gray-200 text-gray-500 hover:text-gray-700',
            ]"
          >
            {{ f === 'all' ? `全部 (${counts.all})` : f === 'favorited' ? `已收藏 (${counts.favorited})` : `已删除 (${counts.deleted})` }}
          </button>
          <button
            @click="cycleThumbSize"
            :class="['px-3 py-1 rounded-full text-xs font-medium transition-colors', isDark ? 'bg-gray-800 text-gray-400 hover:text-gray-200' : 'bg-gray-200 text-gray-500 hover:text-gray-700']"
          >
            缩略图: {{ thumbSizeLabel }}
          </button>
        </div>
        <div class="flex items-center gap-2">
          <button @click="selectAll" class="px-3 py-1 text-xs text-gray-400 hover:text-white transition-colors">
            {{ selected.size === items.length && items.length > 0 ? '取消全选' : '全选' }}
          </button>
          <button @click="doBatch('favorite')" class="px-3 py-1 bg-pink-600/20 text-pink-400 rounded text-xs hover:bg-pink-600/30">批量收藏</button>
          <button @click="doBatch('delete')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">批量删除</button>
          <button @click="doBatch('unfavorite')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">取消收藏</button>
          <button @click="doBatch('undelete')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">取消删除</button>
        </div>
      </div>

      <!-- 列表 -->
      <div v-if="items.length === 0 && loading" class="py-12 text-center text-gray-500">加载中...</div>
      <div v-else-if="items.length === 0" class="py-12 text-center text-gray-500">暂无数据</div>
      <div v-else :class="['border rounded-xl overflow-hidden', isDark ? 'border-gray-800' : 'border-gray-200']">
        <div
          v-for="(item, idx) in items"
          :key="item.id"
          :class="['flex items-center gap-4 px-4 py-3 transition-colors cursor-pointer', isDark ? 'hover:bg-gray-900/50' : 'hover:bg-gray-100', idx > 0 ? (isDark ? 'border-t border-gray-800' : 'border-t border-gray-200') : '']"
          @click="openPreview(item)"
        >
          <input
            type="checkbox"
            :checked="selected.has(item.id)"
            @change="toggleSelect(item.id)"
            @click.stop
            class="w-4 h-4 accent-blue-500 shrink-0"
          />
          <img
            :src="item.media_type === 'video' && item.thumbnail_path ? getThumbnailUrl(item.id) : getStreamUrl(item.id)"
            :class="[thumbClasses, 'object-cover rounded shrink-0']"
          />
          <div class="flex-1 min-w-0">
            <p class="text-sm truncate">{{ item.file_path.split(/[/\\]/).pop() }}</p>
            <p class="text-xs text-gray-500">{{ item.media_type }} · {{ (item.size_bytes / 1024).toFixed(0) }}KB</p>
          </div>
          <div class="flex items-center gap-2 shrink-0" @click.stop>
            <span v-if="item.is_favorited" class="text-xs text-pink-400">已收藏</span>
            <span v-if="item.is_deleted" class="text-xs text-red-400">已删除</span>
            <button @click="doToggleFavorite(item.id)" class="p-1 text-gray-500 hover:text-pink-400 transition-colors" :title="item.is_favorited ? '取消收藏' : '收藏'">
              <svg class="w-4 h-4" :fill="item.is_favorited ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
              </svg>
            </button>
            <button @click="doToggleDelete(item.id)" class="p-1 text-gray-500 hover:text-red-400 transition-colors" :title="item.is_deleted ? '取消删除' : '标记删除'">
              <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z" />
              </svg>
            </button>
          </div>
        </div>
      </div>

      <!-- Infinite scroll sentinel -->
      <div ref="sentinelRef" class="h-1" />
      <div v-if="loading && items.length > 0" class="py-4 text-center text-gray-500 text-sm">加载中...</div>
      <div v-if="!hasMore && items.length > 0" class="py-4 text-center text-gray-500 text-xs">已加载全部</div>
    </main>

    <!-- Preview modal -->
    <Teleport to="body">
      <div
        v-if="previewItem"
        class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
        @click="closePreview"
      >
        <button
          @click="closePreview"
          class="fixed top-4 right-4 text-white/70 hover:text-white text-3xl z-10"
        >
          &times;
        </button>
        <video
          v-if="previewItem.media_type === 'video'"
          :src="getStreamUrl(previewItem.id)"
          controls
          autoplay
          class="max-w-full max-h-full rounded-lg"
          @click.stop
        />
        <img
          v-else
          :src="getStreamUrl(previewItem.id)"
          class="max-w-full max-h-full object-contain rounded-lg"
          @click.stop
        />
      </div>
    </Teleport>
  </div>
</template>
