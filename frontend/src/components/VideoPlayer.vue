<script setup lang="ts">
import type { MediaItem } from '../api/types'
import { getStreamUrl } from '../api/client'
import { ref, watch, onUnmounted } from 'vue'
import VideoProgress from './VideoProgress.vue'

const props = defineProps<{ item: MediaItem }>()
const emit = defineEmits<{ close: [] }>()
const videoEl = ref<HTMLVideoElement | null>(null)
const videoPaused = ref(true)

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) emit('close')
}

function onKeydown(e: KeyboardEvent) {
  if (!videoEl.value || props.item.media_type !== 'video') return
  if (e.key === 'j') videoEl.value.currentTime = Math.max(0, videoEl.value.currentTime - 30)
  else if (e.key === 'k') videoEl.value.currentTime = Math.min(videoEl.value.duration || 0, videoEl.value.currentTime + 30)
}

watch(() => props.item, () => {
  window.addEventListener('keydown', onKeydown)
}, { immediate: true })

onUnmounted(() => window.removeEventListener('keydown', onKeydown))
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
    <template v-if="item.media_type === 'video'">
      <div class="relative max-w-full max-h-[calc(100vh-2rem)]">
        <video
          ref="videoEl"
          :src="getStreamUrl(item.id)"
          autoplay
          class="max-w-full max-h-[calc(100vh-2rem)] rounded-lg"
          @click.stop="videoEl && (videoEl.paused ? videoEl.play() : videoEl.pause())"
          @pause="videoPaused = true"
          @play="videoPaused = false"
        />
        <div
          v-if="videoPaused"
          class="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <div class="w-20 h-20 rounded-full bg-black/40 flex items-center justify-center">
            <svg class="w-10 h-10 text-white ml-1" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
          </div>
        </div>
      </div>
      <div class="fixed bottom-0 inset-x-0 z-10 px-4 pb-4">
        <VideoProgress :video="videoEl" />
      </div>
    </template>
    <img
      v-else
      :src="getStreamUrl(item.id)"
      class="max-w-full max-h-full object-contain rounded-lg cursor-pointer"
      @click="emit('close')"
    />
  </div>
</template>
