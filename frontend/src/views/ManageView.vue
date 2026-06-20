<script setup lang="ts">
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import type { ExportTag, MediaItem } from '../api/types'
import { fetchFeed, getThumbnailUrl, getStreamUrl, getPreviewUrl, purgeDeleted, exportMedia, batchUpdate, toggleFavorite, toggleDelete, toggleDamaged } from '../api/client'
import { useTheme } from '../composables/useTheme'
import { useThumbnailMode } from '../composables/useThumbnailMode'
import VideoProgress from '../components/VideoProgress.vue'
import { releaseMediaElement } from '../utils/mediaResource'

type ThumbSize = 'small' | 'medium' | 'large'

const { isDark } = useTheme()
const { thumbMode } = useThumbnailMode()

const items = ref<MediaItem[]>([])
const filterFav = ref(false)
const filterDel = ref(false)
const filterDamaged = ref(false)
const selected = ref<Set<string>>(new Set())
const exportDir = ref('')
const exportTags = ref<ExportTag[]>(['favorited'])
const showExportOptions = ref(false)
const message = ref('')
const loading = ref(false)
const hasMore = ref(true)
const page = ref(1)
const currentTotal = ref(0)
const thumbSize = ref<ThumbSize>('small')
const previewItem = ref<MediaItem | null>(null)
const previewVideoEl = ref<HTMLVideoElement | null>(null)
const previewPaused = ref(true)
const counts = ref({ all: 0, favorited: 0, deleted: 0, damaged: 0 })
const sentinelRef = ref<HTMLElement>()
let observer: IntersectionObserver | null = null

const PAGE_SIZE = 300
const exportOptions: ExportTag[] = ['favorited', 'deleted', 'damaged']
const exportLabelMap: Record<ExportTag, string> = {
  favorited: '已收藏',
  deleted: '已删除',
  damaged: '已损坏',
}

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

const exportSelectionLabel = computed(() => (
  exportTags.value.length
    ? exportTags.value.map(tag => exportLabelMap[tag]).join('、')
    : '未选择'
))

function formatMediaSize(bytes: number) {
  const units = ['KB', 'MB', 'GB']
  let value = bytes / 1024
  let unitIndex = 0
  while (value >= 1024 && unitIndex < units.length - 1) {
    value /= 1024
    unitIndex++
  }
  const formatter = new Intl.NumberFormat('zh-CN', {
    maximumFractionDigits: value >= 100 ? 0 : value >= 10 ? 1 : 2,
  })
  return `${formatter.format(value)}${units[unitIndex]}`
}

function cycleThumbSize() {
  const sizes: ThumbSize[] = ['small', 'medium', 'large']
  thumbSize.value = sizes[(sizes.indexOf(thumbSize.value) + 1) % 3]
}

async function loadCounts() {
  try {
    const [all, fav, del, damaged] = await Promise.all([
      fetchFeed({ page: 1, page_size: 1 }),
      fetchFeed({ page: 1, page_size: 1, is_favorited: true }),
      fetchFeed({ page: 1, page_size: 1, is_deleted: true }),
      fetchFeed({ page: 1, page_size: 1, is_damaged: true }),
    ])
    counts.value = { all: all.total, favorited: fav.total, deleted: del.total, damaged: damaged.total }
  } catch { /* loadCounts 失败不阻塞页面 */ }
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
    if (filterFav.value) params.is_favorited = true
    if (filterDel.value) params.is_deleted = true
    if (filterDamaged.value) params.is_damaged = true

    const res = await fetchFeed(params as Parameters<typeof fetchFeed>[0])
    if (reset) items.value = res.items
    else items.value.push(...res.items)
    currentTotal.value = res.total
    hasMore.value = res.has_next
    page.value++
  } finally {
    loading.value = false
  }
}

async function setFilter(fav: boolean, del: boolean, damaged: boolean) {
  filterFav.value = fav
  filterDel.value = del
  filterDamaged.value = damaged
  selected.value.clear()
  await loadItems(true)
}

function toggleExportTag(tag: ExportTag) {
  if (exportTags.value.includes(tag)) {
    exportTags.value = exportTags.value.filter(item => item !== tag)
  } else {
    exportTags.value = [...exportTags.value, tag]
  }
}

function getExportCount(tag: ExportTag) {
  if (tag === 'favorited') return counts.value.favorited
  if (tag === 'deleted') return counts.value.deleted
  return counts.value.damaged
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
  if (!counts.value.deleted) {
    message.value = '没有需要清理的已删除文件'
    setTimeout(() => message.value = '', 3000)
    return
  }
  if (!confirm(`确定物理删除 ${counts.value.deleted} 个文件？此操作不可撤销。`)) return
  try {
    const res = await purgeDeleted()
    message.value = `已删除 ${res.deleted_count} 个文件`
    await Promise.all([loadItems(true), loadCounts()])
  } catch (e: any) {
    message.value = e.message || '清理失败'
  }
  setTimeout(() => message.value = '', 3000)
}

async function doExport() {
  if (!exportDir.value.trim()) { message.value = '请输入导出目录路径'; setTimeout(() => message.value = '', 3000); return }
  if (!exportTags.value.length) { message.value = '请选择导出标签'; setTimeout(() => message.value = '', 3000); return }
  const res = await exportMedia(exportDir.value.trim(), exportTags.value)
  message.value = `已导出 ${res.exported_count} 个文件到 ${exportDir.value}`
  showExportOptions.value = false
  setTimeout(() => message.value = '', 5000)
}

async function doToggleFavorite(id: string) {
  const updated = await toggleFavorite(id)
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
  loadCounts()
  if (filterFav.value) await loadItems(true)
}

async function doToggleDelete(id: string) {
  const updated = await toggleDelete(id)
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
  loadCounts()
  if (filterDel.value) await loadItems(true)
}

async function doToggleDamaged(id: string) {
  const updated = await toggleDamaged(id)
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
  loadCounts()
  if (filterDamaged.value) await loadItems(true)
}

function openPreview(item: MediaItem) {
  previewItem.value = item
}

function closePreview() {
  releaseMediaElement(previewVideoEl.value)
  previewItem.value = null
}

function onPreviewKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') closePreview()
  else if (previewItem.value?.media_type === 'video' && previewVideoEl.value) {
    if (e.key === 'j') previewVideoEl.value.currentTime = Math.max(0, previewVideoEl.value.currentTime - 30)
    else if (e.key === 'k') previewVideoEl.value.currentTime = Math.min(previewVideoEl.value.duration || 0, previewVideoEl.value.currentTime + 30)
  }
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
  releaseMediaElement(previewVideoEl.value)
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
        <div class="relative flex items-center gap-2">
          <input
            v-model="exportDir"
            placeholder="导出到目录..."
            :class="['px-3 py-2 border rounded-lg text-sm placeholder-gray-500 w-64', isDark ? 'bg-gray-800 border-gray-700 text-white' : 'bg-white border-gray-300 text-gray-900']"
          />
          <button
            @click="showExportOptions = !showExportOptions"
            class="px-4 py-2 bg-pink-600/20 text-pink-400 border border-pink-600/30 rounded-lg text-sm hover:bg-pink-600/30 transition-colors"
          >
            导出
          </button>
          <div
            v-if="showExportOptions"
            :class="['absolute top-full right-0 mt-2 w-64 p-3 border rounded-lg shadow-xl z-20', isDark ? 'bg-gray-900 border-gray-700' : 'bg-white border-gray-200']"
          >
            <p class="text-xs text-gray-500 mb-2">导出内容: {{ exportSelectionLabel }}</p>
            <label
              v-for="tag in exportOptions"
              :key="tag"
              class="flex items-center justify-between gap-3 py-1.5 text-sm cursor-pointer"
            >
              <span>{{ exportLabelMap[tag] }} ({{ getExportCount(tag) }})</span>
              <input
                type="checkbox"
                :checked="exportTags.includes(tag)"
                class="w-4 h-4 accent-pink-500"
                @change="toggleExportTag(tag)"
              />
            </label>
            <button
              @click="doExport"
              class="mt-3 w-full px-3 py-2 bg-pink-600 text-white rounded-lg text-sm hover:bg-pink-500 transition-colors"
            >
              确认导出
            </button>
          </div>
        </div>
      </div>

      <!-- 筛选 + 批量操作 + 缩略图尺寸 -->
      <div class="flex items-center justify-between mb-4">
        <div class="flex items-center gap-2">
          <button
            @click="setFilter(false, false, false)"
            :class="[
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              !filterFav && !filterDel && !filterDamaged ? 'bg-blue-600 text-white' : isDark ? 'bg-gray-800 text-gray-400 hover:text-gray-200' : 'bg-gray-200 text-gray-500 hover:text-gray-700',
            ]"
          >
            全部 ({{ counts.all }})
          </button>
          <button
            @click="setFilter(!filterFav, filterDel, filterDamaged)"
            :class="[
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              filterFav ? 'bg-pink-600 text-white' : isDark ? 'bg-gray-800 text-gray-400 hover:text-gray-200' : 'bg-gray-200 text-gray-500 hover:text-gray-700',
            ]"
          >
            已收藏 ({{ counts.favorited }})
          </button>
          <button
            @click="setFilter(filterFav, !filterDel, filterDamaged)"
            :class="[
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              filterDel ? 'bg-red-600 text-white' : isDark ? 'bg-gray-800 text-gray-400 hover:text-gray-200' : 'bg-gray-200 text-gray-500 hover:text-gray-700',
            ]"
          >
            已删除 ({{ counts.deleted }})
          </button>
          <button
            @click="setFilter(filterFav, filterDel, !filterDamaged)"
            :class="[
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              filterDamaged ? 'bg-purple-600 text-white' : isDark ? 'bg-gray-800 text-gray-400 hover:text-gray-200' : 'bg-gray-200 text-gray-500 hover:text-gray-700',
            ]"
          >
            已损坏 ({{ counts.damaged }})
          </button>
          <span v-if="filterFav || filterDel || filterDamaged" class="text-xs text-gray-500">
            当前筛选: {{ currentTotal }} 项
          </span>
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
          <button @click="doBatch('damage')" class="px-3 py-1 bg-purple-600/20 text-purple-400 rounded text-xs hover:bg-purple-600/30">标记损坏</button>
          <button @click="doBatch('unfavorite')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">取消收藏</button>
          <button @click="doBatch('undelete')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">取消删除</button>
          <button @click="doBatch('undamage')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">取消损坏</button>
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
            v-if="item.media_type === 'image'"
            :src="getStreamUrl(item.id)"
            :class="[thumbClasses, 'object-cover rounded shrink-0']"
          />
          <template v-else>
            <img
              v-if="thumbMode === 'grid' && item.preview_path"
              :src="getPreviewUrl(item.id)"
              :class="[thumbClasses, 'object-cover rounded shrink-0']"
            />
            <img
              v-else-if="thumbMode !== 'grid' && item.thumbnail_path"
              :src="getThumbnailUrl(item.id)"
              :class="[thumbClasses, 'object-cover rounded shrink-0']"
            />
            <div
              v-else-if="thumbMode === 'grid' && !item.preview_path"
              :class="[thumbClasses, 'bg-black flex items-center justify-center rounded shrink-0']"
            >
              <span class="text-white text-[8px] text-center leading-tight px-1">未生成</span>
            </div>
            <div
              v-else
              :class="[thumbClasses, 'object-cover rounded shrink-0']"
              class="bg-black flex items-center justify-center"
            >
              <span class="text-white text-[8px] text-center leading-tight px-1">未生成</span>
            </div>
          </template>
          <div class="flex-1 min-w-0">
            <p class="text-sm truncate">{{ item.file_path.split(/[/\\]/).pop() }}</p>
            <p class="text-xs text-gray-500">{{ item.media_type }} · {{ formatMediaSize(item.size_bytes) }}</p>
          </div>
          <div class="flex items-center gap-2 shrink-0" @click.stop>
            <span v-if="item.is_favorited" class="text-xs text-pink-400">已收藏</span>
            <span v-if="item.is_deleted" class="text-xs text-red-400">已删除</span>
            <span v-if="item.is_damaged" class="text-xs text-purple-400">已损坏</span>
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
            <button @click="doToggleDamaged(item.id)" class="p-1 text-gray-500 hover:text-purple-400 transition-colors" :title="item.is_damaged ? '取消损坏标记' : '标记损坏'">
              <svg class="w-4 h-4" :fill="item.is_damaged ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                <path d="M12 9v4M12 17h.01" />
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
        <template v-if="previewItem.media_type === 'video'">
          <div class="relative max-w-full max-h-full">
            <video
              ref="previewVideoEl"
              :src="getStreamUrl(previewItem.id)"
              autoplay
              class="max-w-full max-h-full rounded-lg"
              @click.stop="previewVideoEl && (previewVideoEl.paused ? previewVideoEl.play() : previewVideoEl.pause())"
              @pause="previewPaused = true"
              @play="previewPaused = false"
            />
            <div
              v-if="previewPaused"
              class="absolute inset-0 flex items-center justify-center pointer-events-none"
            >
              <div class="w-20 h-20 rounded-full bg-black/40 flex items-center justify-center">
                <svg class="w-10 h-10 text-white ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
              </div>
            </div>
          </div>
          <div class="fixed bottom-0 inset-x-0 z-10 px-4 pb-4">
            <VideoProgress :video="previewVideoEl" />
          </div>
        </template>
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
