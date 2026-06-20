<script setup lang="ts">
import type { MediaItem } from '../api/types'
import { getStreamUrl, getThumbnailUrl, getPreviewUrl, toggleFavorite, toggleDelete } from '../api/client'
import { useThumbnailMode } from '../composables/useThumbnailMode'

const props = defineProps<{ item: MediaItem }>()
const emit = defineEmits<{ click: [item: MediaItem]; updated: [item: MediaItem] }>()
const { thumbMode } = useThumbnailMode()

function btnInactive() {
  return 'bg-black/45 border-white/40 text-white/80 hover:bg-black/65 hover:border-white/70 hover:text-white'
}

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
  <div class="rounded-lg overflow-hidden cursor-pointer group" @click="emit('click', item)">
    <div class="relative">
      <img
        v-if="item.media_type === 'image'"
        :src="getStreamUrl(item.id)"
        :alt="'Media ' + item.id"
        class="w-full block"
        loading="lazy"
      />
      <template v-else>
        <template v-if="thumbMode === 'grid'">
          <img
            v-if="item.preview_path"
            :src="getPreviewUrl(item.id)"
            :alt="'Preview ' + item.id"
            class="w-full block"
            loading="lazy"
          />
          <div
            v-else
            class="w-full bg-black flex items-center justify-center"
            style="aspect-ratio: 16/9"
          >
            <span class="text-white text-xs text-center px-2">还未生成对应缩略图</span>
          </div>
        </template>
        <template v-else>
          <img
            v-if="item.thumbnail_path"
            :src="getThumbnailUrl(item.id)"
            :alt="'Cover ' + item.id"
            class="w-full block"
            loading="lazy"
          />
          <div
            v-else
            class="w-full bg-black flex items-center justify-center"
            style="aspect-ratio: 16/9"
          >
            <span class="text-white text-xs text-center px-2">还未生成对应缩略图</span>
          </div>
        </template>
        <div class="absolute inset-0 flex items-center justify-center bg-black/20 group-hover:bg-black/40 transition-colors pointer-events-none">
          <svg class="w-10 h-10 text-white/70" fill="currentColor" viewBox="0 0 24 24">
            <path d="M8 5v14l11-7z" />
          </svg>
        </div>
      </template>
      <div class="absolute right-2 bottom-2 z-10 flex items-center gap-1.5">
        <button
          @click="onDelete"
          :class="[
            'w-8 h-8 flex items-center justify-center rounded-full border shadow-lg backdrop-blur-sm transition-colors',
            item.is_deleted
              ? 'bg-red-500/90 border-red-300 text-white'
              : btnInactive(),
          ]"
          :title="item.is_deleted ? '取消删除' : '标记删除'"
        >
          <svg class="w-3.5 h-3.5" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M3 6h18M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2m3 0v14a2 2 0 01-2 2H7a2 2 0 01-2-2V6h14z" />
          </svg>
        </button>
        <button
          @click="onFavorite"
          :class="[
            'w-8 h-8 flex items-center justify-center rounded-full border shadow-lg backdrop-blur-sm transition-colors',
            item.is_favorited
              ? 'bg-yellow-400/90 border-yellow-200 text-white'
              : btnInactive(),
          ]"
          :title="item.is_favorited ? '取消收藏' : '收藏'"
        >
          <svg class="w-3.5 h-3.5" :fill="item.is_favorited ? 'currentColor' : 'none'" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
            <path d="M20.84 4.61a5.5 5.5 0 00-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 00-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78 1.06-1.06a5.5 5.5 0 000-7.78z" />
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>
