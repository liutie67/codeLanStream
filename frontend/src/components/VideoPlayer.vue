<script setup lang="ts">
import type { MediaItem } from '../api/types'
import { getStreamUrl } from '../api/client'

defineProps<{ item: MediaItem }>()
const emit = defineEmits<{ close: [] }>()

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit('close')
}
</script>

<template>
  <div
    class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
    @click="onBackdropClick"
  >
    <button
      @click="emit('close')"
      class="fixed top-4 right-4 text-white/70 hover:text-white text-3xl z-10"
    >
      &times;
    </button>
    <video
      v-if="item.media_type === 'video'"
      :src="getStreamUrl(item.id)"
      controls
      autoplay
      class="max-w-full max-h-full rounded-lg"
      @click.stop
    />
    <img
      v-else
      :src="getStreamUrl(item.id)"
      class="max-w-full max-h-full object-contain rounded-lg cursor-pointer"
      @click="emit('close')"
    />
  </div>
</template>
