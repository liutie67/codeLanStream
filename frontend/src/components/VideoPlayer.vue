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
    class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center"
    @click="onBackdropClick"
  >
    <div class="relative w-full max-w-4xl mx-4">
      <button
        @click="emit('close')"
        class="absolute -top-10 right-0 text-white/70 hover:text-white text-2xl"
      >
        &times;
      </button>
      <video
        v-if="item.media_type === 'video'"
        :src="getStreamUrl(item.id)"
        controls
        autoplay
        class="w-full rounded-lg"
      />
      <img
        v-else
        :src="getStreamUrl(item.id)"
        class="w-full rounded-lg"
      />
    </div>
  </div>
</template>
