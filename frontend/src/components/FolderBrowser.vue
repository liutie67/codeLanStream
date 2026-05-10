<script setup lang="ts">
import { ref, onMounted } from 'vue'
import type { BrowseRoot, MediaItem, MediaType } from '../api/types'
import { fetchBrowse } from '../api/client'
import { useTheme } from '../composables/useTheme'
import TypeFilter from './TypeFilter.vue'
import MediaCard from './MediaCard.vue'

const emit = defineEmits<{ close: []; play: [item: MediaItem] }>()
const { isDark } = useTheme()

const roots = ref<BrowseRoot[]>([])
const currentPath = ref<string[]>([])
const currentRoot = ref('')
const folders = ref<string[]>([])
const items = ref<MediaItem[]>([])
const loading = ref(false)
const showRoots = ref(true)
const mediaType = ref<MediaType | null>(null)
const colMode = ref<'auto' | '1' | '2'>('auto')

function getColClass() {
  if (colMode.value === '1') return 'masonry masonry-1'
  if (colMode.value === '2') return 'masonry masonry-2'
  return 'masonry'
}

function cycleColMode() {
  const modes: ('auto' | '1' | '2')[] = ['auto', '1', '2']
  const idx = modes.indexOf(colMode.value)
  colMode.value = modes[(idx + 1) % modes.length]
}

const colIcon = () => {
  const map = { auto: '⊞', '1': '▭', '2': '⊞' }
  return map[colMode.value]
}

function setMediaType(type: MediaType | null) {
  mediaType.value = type
  if (!showRoots.value) loadFolder()
}

onMounted(loadRoots)

async function loadRoots() {
  loading.value = true
  const res = await fetchBrowse()
  roots.value = res.roots
  showRoots.value = true
  loading.value = false
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
  currentPath.value = []
  currentRoot.value = ''
  showRoots.value = true
  folders.value = []
  items.value = []
}

async function navigateTo(idx: number) {
  currentPath.value = currentPath.value.slice(0, idx + 1)
  await loadFolder()
}

async function loadFolder() {
  loading.value = true
  const subdir = currentPath.value.length > 1 ? currentPath.value.slice(1).join('/') : undefined
  const res = await fetchBrowse(currentRoot.value, subdir, mediaType.value)
  folders.value = res.folders
  items.value = res.items
  loading.value = false
}

function onItemUpdated(updated: MediaItem) {
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
}
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
          <div v-if="!showRoots" class="flex items-center gap-2 shrink-0">
            <span class="text-xs text-gray-500 tabular-nums">{{ items.length }}</span>
            <button
              @click="cycleColMode"
              :class="['w-7 h-7 flex items-center justify-center rounded-full text-sm transition-colors shrink-0', isDark ? 'bg-gray-800 text-gray-400 hover:bg-gray-700' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']"
              :title="colMode === 'auto' ? '自动' : colMode === '1' ? '单列' : '双列'"
            >{{ colIcon() }}</button>
            <TypeFilter :current="mediaType" @change="setMediaType" />
          </div>
        </div>
      </header>

      <main class="px-4 lg:px-6 py-4">
        <div v-if="loading" class="py-12 text-center text-gray-400">加载中...</div>

        <div v-else-if="showRoots" class="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
          <button
            v-for="root in roots"
            :key="root.path"
            @click="enterRoot(root)"
            :class="['p-4 rounded-xl border text-left transition-colors', isDark ? 'bg-gray-900 border-gray-800 hover:bg-gray-800' : 'bg-white border-gray-200 hover:bg-gray-100']"
          >
            <svg class="w-8 h-8 mb-2 text-yellow-400" fill="currentColor" viewBox="0 0 24 24">
              <path d="M10 4H4a2 2 0 00-2 2v12a2 2 0 002 2h16a2 2 0 002-2V8a2 2 0 00-2-2h-8l-2-2z"/>
            </svg>
            <p class="text-sm font-medium truncate">{{ root.name }}</p>
            <p class="text-xs text-gray-500">{{ root.count }} 个文件</p>
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

          <div v-if="items.length" :class="getColClass()">
            <MediaCard
              v-for="item in items"
              :key="item.id"
              :item="item"
              @click="emit('play', $event)"
              @updated="onItemUpdated"
            />
          </div>
          <div v-else-if="!folders.length" class="py-12 text-center text-gray-500">此目录无媒体文件</div>
        </template>
      </main>
    </div>
  </div>
</template>
