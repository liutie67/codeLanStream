<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { RouterLink } from 'vue-router'
import type { MediaItem } from '../api/types'
import { fetchFeed, getThumbnailUrl, getStreamUrl, purgeDeleted, exportFavorites, batchUpdate, toggleFavorite, toggleDelete } from '../api/client'
import { useTheme } from '../composables/useTheme'

type FilterMode = 'all' | 'favorited' | 'deleted'

const { isDark } = useTheme()
const allItems = ref<MediaItem[]>([])
const filter = ref<FilterMode>('all')
const selected = ref<Set<string>>(new Set())
const exportDir = ref('')
const message = ref('')
const loading = ref(false)

const filteredItems = () => {
  if (filter.value === 'favorited') return allItems.value.filter(i => i.is_favorited)
  if (filter.value === 'deleted') return allItems.value.filter(i => i.is_deleted)
  return allItems.value
}

const deletedCount = () => allItems.value.filter(i => i.is_deleted).length
const favoritedCount = () => allItems.value.filter(i => i.is_favorited).length

async function loadAll() {
  loading.value = true
  let page = 1
  allItems.value = []
  while (true) {
    const res = await fetchFeed({ page, page_size: 100 })
    allItems.value.push(...res.items)
    if (!res.has_next) break
    page++
  }
  loading.value = false
}

function toggleSelect(id: string) {
  if (selected.value.has(id)) selected.value.delete(id)
  else selected.value.add(id)
}

function selectAll() {
  const items = filteredItems()
  if (selected.value.size === items.length) {
    selected.value.clear()
  } else {
    selected.value = new Set(items.map(i => i.id))
  }
}

async function doBatch(action: string) {
  if (selected.value.size === 0) return
  await batchUpdate([...selected.value], action)
  message.value = `已更新 ${selected.value.size} 项`
  selected.value.clear()
  await loadAll()
  setTimeout(() => message.value = '', 3000)
}

async function doPurge() {
  const count = deletedCount()
  if (!count || !confirm(`确定物理删除 ${count} 个文件？此操作不可撤销。`)) return
  const res = await purgeDeleted()
  message.value = `已删除 ${res.deleted_count} 个文件`
  await loadAll()
  setTimeout(() => message.value = '', 3000)
}

async function doExport() {
  if (!exportDir.value.trim()) { message.value = '请输入导出目录路径'; setTimeout(() => message.value = '', 3000); return }
  const res = await exportFavorites(exportDir.value.trim())
  message.value = `已导出 ${res.exported_count} 个文件到 ${exportDir.value}`
  setTimeout(() => message.value = '', 5000)
}

async function doToggleFavorite(id: string) {
  await toggleFavorite(id)
  await loadAll()
}

async function doToggleDelete(id: string) {
  await toggleDelete(id)
  await loadAll()
}

onMounted(loadAll)
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
          一键清理已删除 ({{ deletedCount() }})
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
            导出收藏 ({{ favoritedCount() }})
          </button>
        </div>
      </div>

      <!-- 筛选 + 批量操作 -->
      <div class="flex items-center justify-between mb-4">
        <div class="flex gap-2">
          <button
            v-for="f in (['all', 'favorited', 'deleted'] as FilterMode[])"
            :key="f"
            @click="filter = f"
            :class="[
              'px-3 py-1 rounded-full text-xs font-medium transition-colors',
              filter === f ? 'bg-blue-600 text-white' : isDark ? 'bg-gray-800 text-gray-400 hover:text-gray-200' : 'bg-gray-200 text-gray-500 hover:text-gray-700',
            ]"
          >
            {{ f === 'all' ? `全部 (${allItems.length})` : f === 'favorited' ? `已收藏 (${favoritedCount()})` : `已删除 (${deletedCount()})` }}
          </button>
        </div>
        <div class="flex items-center gap-2">
          <button @click="selectAll" class="px-3 py-1 text-xs text-gray-400 hover:text-white transition-colors">
            {{ selected.size === filteredItems().length && filteredItems().length > 0 ? '取消全选' : '全选' }}
          </button>
          <button @click="doBatch('favorite')" class="px-3 py-1 bg-pink-600/20 text-pink-400 rounded text-xs hover:bg-pink-600/30">批量收藏</button>
          <button @click="doBatch('delete')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">批量删除</button>
          <button @click="doBatch('unfavorite')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">取消收藏</button>
          <button @click="doBatch('undelete')" :class="['px-3 py-1 rounded text-xs', isDark ? 'bg-gray-700 text-gray-300 hover:bg-gray-600' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']">取消删除</button>
        </div>
      </div>

      <!-- 列表 -->
      <div v-if="loading" class="py-12 text-center text-gray-500">加载中...</div>
      <div v-else-if="filteredItems().length === 0" class="py-12 text-center text-gray-500">暂无数据</div>
      <div v-else :class="['border rounded-xl overflow-hidden', isDark ? 'border-gray-800' : 'border-gray-200']">
        <div
          v-for="(item, idx) in filteredItems()"
          :key="item.id"
          :class="['flex items-center gap-4 px-4 py-3 transition-colors', isDark ? 'hover:bg-gray-900/50' : 'hover:bg-gray-100', idx > 0 ? (isDark ? 'border-t border-gray-800' : 'border-t border-gray-200') : '']"
        >
          <input
            type="checkbox"
            :checked="selected.has(item.id)"
            @change="toggleSelect(item.id)"
            class="w-4 h-4 accent-blue-500 shrink-0"
          />
          <img
            :src="item.media_type === 'video' && item.thumbnail_path ? getThumbnailUrl(item.id) : getStreamUrl(item.id)"
            class="w-16 h-12 object-cover rounded shrink-0"
          />
          <div class="flex-1 min-w-0">
            <p class="text-sm truncate">{{ item.file_path.split('/').pop() }}</p>
            <p class="text-xs text-gray-500">{{ item.media_type }} · {{ (item.size_bytes / 1024).toFixed(0) }}KB</p>
          </div>
          <div class="flex items-center gap-2 shrink-0">
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
    </main>
  </div>
</template>
