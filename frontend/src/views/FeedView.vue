<script setup lang="ts">
import { ref } from 'vue'
import type { MediaItem } from '../api/types'
import { useFeed } from '../composables/useFeed'
import TypeFilter from '../components/TypeFilter.vue'
import MediaCard from '../components/MediaCard.vue'
import LoadMore from '../components/LoadMore.vue'
import VideoPlayer from '../components/VideoPlayer.vue'

const { items, loading, hasMore, total, mediaType, loadMore, setMediaType } = useFeed()
const activeItem = ref<MediaItem | null>(null)
</script>

<template>
  <div class="min-h-screen bg-gray-950 text-white">
    <header class="sticky top-0 z-40 bg-gray-950/90 backdrop-blur border-b border-gray-800">
      <div class="max-w-6xl mx-auto px-4 py-3 flex items-center justify-between">
        <h1 class="text-xl font-bold tracking-tight">LanStream</h1>
        <div class="flex items-center gap-4">
          <span class="text-sm text-gray-400">{{ total }} 个媒体</span>
          <TypeFilter :current="mediaType" @change="setMediaType" />
        </div>
      </div>
    </header>

    <main class="max-w-6xl mx-auto px-4 py-6">
      <div class="masonry">
        <MediaCard
          v-for="item in items"
          :key="item.id"
          :item="item"
          @click="activeItem = $event"
        />
      </div>

      <LoadMore :loading="loading" :has-more="hasMore" @load="loadMore" />
    </main>

    <VideoPlayer
      v-if="activeItem"
      :item="activeItem"
      @close="activeItem = null"
    />
  </div>
</template>
