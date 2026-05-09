<script setup lang="ts">
import type { MediaItem } from '../api/types'
import { getStreamUrl, getThumbnailUrl, toggleFavorite, toggleDelete } from '../api/client'

const props = defineProps<{ item: MediaItem }>()
const emit = defineEmits<{ click: [item: MediaItem]; updated: [item: MediaItem] }>()

async function onFavorite(e: MouseEvent) {
  e.stopPropagation()
  const updated = await toggleFavorite(props.item.id)
  emit('updated', updated)
}

async function onDelete(e: MouseEvent) {
  e.stopPropagation()
  const updated = await toggleDelete(props.item.id)
  emit('updated', updated)
}
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
      <div class="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/40 transition-colors pointer-events-none">
        <svg class="w-10 h-10 text-white/70" fill="currentColor" viewBox="0 0 24 24">
          <path d="M8 5v14l11-7z" />
        </svg>
      </div>
    </div>

    <!-- 操作按钮 -->
    <div class="absolute bottom-2 right-2 flex gap-1.5">
      <button
        @click="onDelete"
        :class="[
          'w-7 h-7 flex items-center justify-center rounded-full border transition-colors',
          item.is_deleted
            ? 'bg-black/80 border-black text-white'
            : 'bg-black/30 border-white/50 text-white/70 hover:border-white hover:text-white',
        ]"
      >
        <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z" />
        </svg>
      </button>
      <button
        @click="onFavorite"
        :class="[
          'w-7 h-7 flex items-center justify-center rounded-full border transition-colors',
          item.is_favorited
            ? 'bg-pink-500/80 border-pink-400 text-white'
            : 'bg-black/30 border-white/50 text-white/70 hover:border-white hover:text-white',
        ]"
      >
        <svg class="w-3.5 h-3.5" :fill="item.is_favorited ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
        </svg>
      </button>
    </div>
  </div>
</template>
