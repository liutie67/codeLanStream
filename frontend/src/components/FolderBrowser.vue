<script setup lang="ts">
import { computed, ref, onMounted, onUnmounted, watch } from 'vue'
import type { BrowseRoot, MediaItem, MediaType } from '../api/types'
import { fetchBrowse } from '../api/client'
import { useTheme } from '../composables/useTheme'
import { useThumbnailMode } from '../composables/useThumbnailMode'
import TypeFilter from './TypeFilter.vue'
import MediaCard from './MediaCard.vue'
import { useImportTask } from '../composables/useImportTask'
import RoamingView from './RoamingView.vue'
import TurboView from './TurboView.vue'
import { createLatestRequest } from '../utils/latestRequest'

type ColumnMode = 'auto' | '1' | '2'

const emit = defineEmits<{
  close: []
  play: [item: MediaItem]
}>()
const { isDark } = useTheme()
const { thumbMode, toggleMode } = useThumbnailMode()

const roots = ref<BrowseRoot[]>([])
const currentPath = ref<string[]>([])
const currentRoot = ref('')
const folders = ref<string[]>([])
const items = ref<MediaItem[]>([])
const loading = ref(false)
const loadingMore = ref(false)
const moreError = ref('')
const page = ref(1)
const afterPath = ref<string>()
const hasNext = ref(false)
const total = ref(0)
const error = ref('')
const requests = createLatestRequest()
const showRoots = ref(true)
const importTask = useImportTask()
const mediaType = ref<MediaType | null>(null)
const colMode = ref<ColumnMode>('auto')
const showRoaming = ref(false)
const showTurbo = ref(false)
const selectedFolder = computed(() => {
  if (showRoots.value) return ''
  const subdir = currentPath.value.slice(1).join('/')
  return subdir ? `${currentRoot.value.replace(/\/$/, '')}/${subdir}` : currentRoot.value
})

const thumbModeTitle = computed(() => (
  thumbMode.value === 'grid' ? '当前: 预览，点击切换到首帧' : '当前: 首帧，点击切换到预览'
))

const colCount = computed(() => {
  if (colMode.value === '1') return 1
  if (colMode.value === '2') return 2
  return 4
})

const columns = computed(() => {
  const cols: MediaItem[][] = Array.from({ length: colCount.value }, () => [])
  for (const item of items.value) {
    const shortest = cols.reduce((min, col, i) =>
      col.length < cols[min].length ? i : min, 0)
    cols[shortest].push(item)
  }
  return cols
})

function cycleColMode() {
  const modes: ColumnMode[] = ['auto', '1', '2']
  const idx = modes.indexOf(colMode.value)
  colMode.value = modes[(idx + 1) % modes.length]
}

function setMediaType(type: MediaType | null) {
  mediaType.value = type
  if (!showRoots.value) loadFolder()
}

onMounted(loadRoots)
onUnmounted(() => requests.cancel())

async function loadRoots() {
  showRoots.value = true
  error.value = ''
  moreError.value = ''
  await requests.run(signal => fetchBrowse(undefined, undefined, undefined, signal), res => {
    roots.value = res.roots
  }, failure => { error.value = failure instanceof Error ? failure.message : '媒体库读取失败' }, value => { loading.value = value })
}

async function enterRoot(root: BrowseRoot) {
  currentRoot.value = root.path
  currentPath.value = [root.name]
  showRoots.value = false
  await loadFolder()
}

async function enterFolder(folder: string) {
  currentPath.value.push(folder)
  await loadFolder()
}

function goHome() {
  requests.cancel()
  currentPath.value = []
  currentRoot.value = ''
  showRoots.value = true
  folders.value = []
  items.value = []
  void loadRoots()
}

async function navigateTo(idx: number) {
  currentPath.value = currentPath.value.slice(0, idx + 1)
  await loadFolder()
}

async function loadFolder() {
  error.value = ''
  folders.value = []
  items.value = []
  moreError.value = ''
  page.value = 1
  afterPath.value = undefined
  hasNext.value = false
  total.value = 0
  const subdir = currentPath.value.length > 1 ? currentPath.value.slice(1).join('/') : undefined
  await requests.run(signal => fetchBrowse(currentRoot.value, subdir, mediaType.value, signal), res => {
    folders.value = res.folders
    items.value = res.items
    total.value = res.total
    hasNext.value = res.has_next
    afterPath.value = res.items.at(-1)?.file_path
  }, failure => { error.value = failure instanceof Error ? failure.message : '目录读取失败' }, value => { loading.value = value })
}

async function loadMore() {
  if (loading.value || loadingMore.value || !hasNext.value || showRoots.value) return
  moreError.value = ''
  const nextPage = page.value + 1
  const subdir = currentPath.value.slice(1).join('/') || undefined
  await requests.run(signal => fetchBrowse(currentRoot.value, subdir, mediaType.value, signal, nextPage, afterPath.value), res => {
    const ids = new Set(items.value.map(item => item.id))
    items.value.push(...res.items.filter(item => !ids.has(item.id)))
    page.value = nextPage
    total.value = res.total
    hasNext.value = res.has_next
    afterPath.value = res.items.at(-1)?.file_path ?? afterPath.value
  }, failure => { moreError.value = failure instanceof Error ? failure.message : '媒体读取失败' }, value => { loadingMore.value = value })
}

function retry() { if (showRoots.value) void loadRoots(); else void loadFolder() }
function goUp() { if (currentPath.value.length > 1) void navigateTo(currentPath.value.length - 2); else goHome() }
function removeUnavailable(id: string) {
  if (items.value.some(item => item.id === id)) total.value = Math.max(0, total.value - 1)
  items.value = items.value.filter(item => item.id !== id)
}

function onItemUpdated(updated: MediaItem) {
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
}

watch(importTask.revision, async () => {
  if (showRoots.value) await loadRoots()
  else await loadFolder()
})
</script>

<template>
  <div class="fixed inset-0 z-50 bg-black/80 overflow-y-auto">
    <div :class="['min-h-screen', isDark ? 'bg-gray-950 text-white' : 'bg-gray-50 text-gray-900']">
      <header :class="['sticky top-0 z-10 backdrop-blur border-b', isDark ? 'bg-gray-950/90 border-gray-800' : 'bg-white/90 border-gray-200']">
        <div class="px-4 py-2 flex items-center justify-between gap-2">
          <div class="flex items-center gap-3 min-w-0">
            <button @click="emit('close')" class="text-gray-400 hover:text-white text-xl shrink-0">&times;</button>
            <nav class="flex items-center gap-1 text-sm overflow-x-auto whitespace-nowrap">
              <button @click="goHome" :class="['shrink-0', showRoots ? 'font-medium' : 'text-gray-400 hover:text-white']">媒体库</button>
              <template v-for="(part, idx) in currentPath" :key="idx">
                <span class="text-gray-600 shrink-0">/</span>
                <button
                  @click="navigateTo(idx)"
                  :class="['shrink-0', idx === currentPath.length - 1 ? 'font-medium' : 'text-gray-400 hover:text-white']"
                >{{ part }}</button>
              </template>
            </nav>
          </div>
          <div class="flex items-center gap-2 shrink-0">
            <button
              @click="importTask.open"
              :class="[
                'h-8 w-8 md:w-auto md:px-2.5 flex items-center justify-center gap-1 rounded-full border text-xs font-medium shadow-sm transition-colors shrink-0',
                isDark ? 'border-gray-700 bg-gray-800 text-emerald-400 hover:text-emerald-300' : 'border-gray-200 bg-white text-gray-600 hover:text-gray-900',
              ]"
              title="导入媒体"
              aria-label="导入媒体"
            >
              <svg class="w-4 h-4 shrink-0" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                <path d="M12 5v10m0 0l-4-4m4 4l4-4" />
                <path d="M5 19h14" />
              </svg>
              <span class="hidden md:inline">导入</span>
            </button>
            <template v-if="!showRoots">
              <span class="text-xs text-gray-500 tabular-nums">{{ items.length }} / {{ total }}</span>
              <button
                @click="showRoaming = true"
                :disabled="loading || !!error || !items.length"
                :class="['w-8 h-8 flex items-center justify-center rounded-full transition-colors shrink-0', isDark ? 'bg-gray-800 text-blue-400 hover:bg-gray-700' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']"
                title="漫游当前文件夹（不含子文件夹）"
                aria-label="漫游当前文件夹"
              >
                <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
                  <path d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z"/><path d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z"/>
                </svg>
              </button>
              <button
                v-if="!showTurbo"
                @click="showTurbo = true"
                :disabled="loading || !!error || !items.length"
                class="flex w-8 h-8 items-center justify-center rounded-full bg-gray-800 text-yellow-400 hover:bg-gray-700 transition-colors shrink-0"
                title="极速浏览当前文件夹（不含子文件夹）"
                aria-label="极速浏览当前文件夹"
              >
                <svg class="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M13 2L3 14h9l-1 8 10-12h-9l1-8z"/>
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
                :title="colMode === 'auto' ? '当前: 自动列数，点击切换到单列' : colMode === '1' ? '当前: 单列，点击切换到双列' : '当前: 双列，点击切换到自动'"
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
            </template>
          </div>
        </div>
      </header>

      <main class="px-4 lg:px-6 py-4">
        <div v-if="loading" class="py-12 text-center text-gray-400">加载中...</div>

        <div v-else-if="error" class="py-12 text-center text-gray-400" role="alert">
          <p>{{ error }}</p>
          <div class="flex justify-center gap-4 mt-4 text-sm text-blue-400">
            <button @click="retry">重试</button>
            <button v-if="!showRoots" @click="goUp">返回上级</button>
            <button @click="goHome">返回媒体库</button>
          </div>
        </div>

        <div v-else-if="showRoots" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <button
            v-for="root in roots"
            :key="root.path"
            @click="enterRoot(root)"
            :class="['p-4 rounded-xl border text-left transition-colors', root.availability !== 'available' ? 'opacity-50' : '', isDark ? 'bg-gray-900 border-gray-800 hover:bg-gray-800' : 'bg-white border-gray-200 hover:bg-gray-100']"
          >
            <svg class="w-8 h-8 mb-2 text-yellow-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/>
            </svg>
            <p class="text-sm font-medium truncate">{{ root.name }}</p>
            <p class="text-xs text-gray-500">{{ root.count }} 个索引文件</p>
            <p v-if="root.availability !== 'available'" class="text-xs text-amber-500 mt-1">暂不可访问 · 点击复查</p>
          </button>
        </div>

        <template v-else>
          <div v-if="folders.length" class="grid grid-cols-3 md:grid-cols-6 lg:grid-cols-8 gap-2 mb-4">
            <button
              v-for="folder in folders"
              :key="folder"
              @click="enterFolder(folder)"
              :class="['p-3 rounded-xl border text-left transition-colors', isDark ? 'bg-gray-900 border-gray-800 hover:bg-gray-800' : 'bg-white border-gray-200 hover:bg-gray-100']"
            >
              <svg class="w-5 h-5 mb-1 text-yellow-400" fill="currentColor" viewBox="0 0 24 24">
                <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/>
              </svg>
              <p class="text-xs font-medium truncate">{{ folder }}</p>
            </button>
          </div>

          <div
            v-if="items.length"
            class="flex items-start gap-3"
            :style="colMode === '1' ? 'max-width: 720px; margin: 0 auto' : ''"
          >
            <div v-for="(col, ci) in columns" :key="ci" class="flex-1 flex flex-col gap-3">
              <MediaCard
                v-for="item in col"
                :key="item.id"
                :item="item"
                @click="emit('play', $event)"
                @updated="onItemUpdated"
                @unavailable="removeUnavailable"
              />
            </div>
          </div>
          <div v-else-if="!folders.length" class="py-12 text-center text-gray-500">此目录无媒体文件</div>
          <div v-if="hasNext" class="text-center py-6">
            <p v-if="moreError" class="text-amber-500 text-sm mb-3" role="alert">{{ moreError }}</p>
            <button :disabled="loadingMore" @click="loadMore" class="text-sm text-blue-400 disabled:opacity-50">
              {{ loadingMore ? '加载中…' : moreError ? '重试加载更多' : '加载更多' }}
            </button>
          </div>
        </template>
      </main>

    </div>
  </div>
  <RoamingView v-if="showRoaming" :folder="selectedFolder" @close="showRoaming = false" />
  <TurboView v-if="showTurbo" :folder="selectedFolder" @close="showTurbo = false" />
</template>
