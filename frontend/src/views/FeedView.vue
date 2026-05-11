<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { RouterLink } from 'vue-router'
import type { MediaItem } from '../api/types'
import { useFeed } from '../composables/useFeed'
import { useTheme } from '../composables/useTheme'
import TypeFilter from '../components/TypeFilter.vue'
import MediaCard from '../components/MediaCard.vue'
import VideoPlayer from '../components/VideoPlayer.vue'
import FolderBrowser from '../components/FolderBrowser.vue'
import RoamingView from '../components/RoamingView.vue'
import TurboView from '../components/TurboView.vue'

const { items, loading, hasMore, total, mediaType, loadMore, setMediaType } = useFeed()
const { isDark, toggleTheme } = useTheme()
const activeItem = ref<MediaItem | null>(null)
const showFolders = ref(false)
const showRoaming = ref(false)
const showTurbo = ref(false)
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

function onItemUpdated(updated: MediaItem) {
  const idx = items.value.findIndex(i => i.id === updated.id)
  if (idx !== -1) items.value[idx] = updated
}

function onScroll() {
  if (loading.value || !hasMore.value) return
  const bottom = document.documentElement.scrollHeight - window.innerHeight - window.scrollY
  if (bottom < 600) loadMore()
}

onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onUnmounted(() => window.removeEventListener('scroll', onScroll))
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
            @click="cycleColMode"
            :class="['w-7 h-7 flex items-center justify-center rounded-full text-sm transition-colors shrink-0', isDark ? 'bg-gray-800 text-gray-400 hover:bg-gray-700' : 'bg-gray-200 text-gray-600 hover:bg-gray-300']"
            :title="colMode === 'auto' ? '自动' : colMode === '1' ? '单列' : '双列'"
          >
            {{ colIcon() }}
          </button>
          <TypeFilter :current="mediaType" @change="setMediaType" />
        </div>
      </div>
    </header>

    <main class="px-4 lg:px-6 py-4">
      <div :class="getColClass()">
        <MediaCard
          v-for="item in items"
          :key="item.id"
          :item="item"
          @click="activeItem = $event"
          @updated="onItemUpdated"
        />
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
