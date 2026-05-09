<script setup lang="ts">
import type { MediaItem } from '../api/types'
import { getStreamUrl } from '../api/client'

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
      <video
        :src="getStreamUrl(item.id)"
        preload="metadata"
        class="w-full block"
        muted
      />
      <div
        class="absolute inset-0 flex items-center justify-center bg-black/30 group-hover:bg-black/50 transition-colors"
      >
        <svg class="w-12 h-12 text-white/80" fill="currentColor" viewBox="0 0 24 24">
          <path d="M8 5v14l11-7z" />
        </svg>
      </div>
    </div>
  </div>
</template>
