<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import type { MediaItem } from '../api/types'
import { useFeed } from '../composables/useFeed'
import TypeFilter from '../components/TypeFilter.vue'
import MediaCard from '../components/MediaCard.vue'
import VideoPlayer from '../components/VideoPlayer.vue'

const { items, loading, hasMore, total, mediaType, loadMore, setMediaType } = useFeed()
const activeItem = ref<MediaItem | null>(null)
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

function onScroll() {
  if (loading.value || !hasMore.value) return
  const bottom = document.documentElement.scrollHeight - window.innerHeight - window.scrollY
  if (bottom < 600) loadMore()
}

onMounted(() => window.addEventListener('scroll', onScroll, { passive: true }))
onUnmounted(() => window.removeEventListener('scroll', onScroll))
</script>

<template>
  <div class="min-h-screen bg-gray-950 text-white">
    <header class="sticky top-0 z-40 bg-gray-950/90 backdrop-blur border-b border-gray-800">
      <div class="max-w-6xl mx-auto px-3 py-2 flex items-center justify-between gap-2">
        <h1 class="text-lg font-bold tracking-tight shrink-0">LanStream</h1>
        <div class="flex items-center gap-2">
          <span class="text-xs text-gray-500 tabular-nums">{{ total }}</span>
          <button
            @click="cycleColMode"
            class="w-7 h-7 flex items-center justify-center rounded-full bg-gray-800 text-gray-400 text-sm hover:bg-gray-700 transition-colors shrink-0"
            :title="colMode === 'auto' ? '自动' : colMode === '1' ? '单列' : '双列'"
          >
            {{ colIcon() }}
          </button>
          <TypeFilter :current="mediaType" @change="setMediaType" />
        </div>
      </div>
    </header>

    <main class="max-w-6xl mx-auto px-3 py-4">
      <div :class="getColClass()">
        <MediaCard
          v-for="item in items"
          :key="item.id"
          :item="item"
          @click="activeItem = $event"
        />
      </div>

      <div v-if="loading" class="py-8 text-center text-gray-400">
        <span class="inline-block animate-spin mr-2">&#9696;</span> 加载中...
      </div>
      <p v-else-if="!hasMore && items.length" class="py-8 text-center text-gray-500 text-sm">已加载全部</p>
    </main>

    <VideoPlayer
      v-if="activeItem"
      :item="activeItem"
      @close="activeItem = null"
    />
  </div>
</template>
