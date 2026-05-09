<script setup lang="ts">
import type { MediaItem } from '../api/types'
import { getStreamUrl, getThumbnailUrl } from '../api/client'

defineProps<{ item: MediaItem }>()
const emit = defineEmits<{ click: [item: MediaItem] }>()
</script>

<template>
  <div
    class="masonry-item rounded-xl overflow-hidden bg-gray-900 cursor-pointer group relative"
    @click="emit('click', item)"
  >
    <img
      v-if="item.media_type === 'image'"
      :src="getStreamUrl(item.id)"
      :alt="'Media ' + item.id"
      class="w-full block"
      loading="lazy"
    />
    <div v-else class="relative">
      <img
        v-if="item.thumbnail_path"
        :src="getThumbnailUrl(item.id)"
        :alt="'Cover ' + item.id"
        class="w-full block"
        loading="lazy"
      />
      <video
        v-else
        :src="getStreamUrl(item.id)"
        preload="metadata"
        class="w-full block"
        muted
      />
      <div
        class="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/40 transition-colors"
      >
        <svg class="w-10 h-10 text-white/70" fill="currentColor" viewBox="0 0 24 24">
          <path d="M8 5v14l11-7z" />
        </svg>
      </div>
    </div>
  </div>
</template>
