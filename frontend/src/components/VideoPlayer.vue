<script setup lang="ts">
import type { MediaItem } from '../api/types'
import { getStreamUrl, recheckMedia } from '../api/client'
import { ref, watch, onMounted, onUnmounted } from 'vue'
import VideoProgress from './VideoProgress.vue'
import { releaseMediaElement } from '../utils/mediaResource'

const props = defineProps<{ item: MediaItem }>()
const emit = defineEmits<{ close: []; unavailable: [id: string] }>()
const failure = ref('')
const retryKey = ref(0)
const videoEl = ref<HTMLVideoElement | null>(null)
const videoPaused = ref(true)

function closePlayer() {
  releaseMediaElement(videoEl.value)
  emit('close')
}

function onBackdropClick(e: MouseEvent) {
  if (e.target === e.currentTarget) closePlayer()
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Escape') { closePlayer(); return }
  if (!videoEl.value || props.item.media_type !== 'video') return
  if (e.key === 'j') videoEl.value.currentTime = Math.max(0, videoEl.value.currentTime - 30)
  else if (e.key === 'k') videoEl.value.currentTime = Math.min(videoEl.value.duration || 0, videoEl.value.currentTime + 30)
}

watch(() => props.item.id, () => {
  failure.value = ''
  releaseMediaElement(videoEl.value)
  videoPaused.value = true
})

async function onError() {
  const id = props.item.id
  failure.value = '媒体加载失败，正在检查原文件…'
  try {
    const [result] = await recheckMedia([id])
    if (props.item.id !== id) return
    if (!result || result.availability !== 'available') emit('unavailable', id)
    else failure.value = '媒体加载失败，请重试或检查文件格式'
  } catch { if (props.item.id === id) failure.value = '无法读取媒体，请检查硬盘或网络后重试' }
}
function retry() { failure.value = ''; retryKey.value++ }

onMounted(() => window.addEventListener('keydown', onKeydown))

onUnmounted(() => {
  releaseMediaElement(videoEl.value)
  window.removeEventListener('keydown', onKeydown)
})
</script>

<template>
  <div
    class="fixed inset-0 z-50 bg-black/80 flex items-center justify-center p-4"
    @click="onBackdropClick"
  >
    <button
      @click="closePlayer"
      class="fixed top-4 right-4 text-white/70 hover:text-white text-3xl z-10"
    >
      &times;
    </button>
    <div v-if="failure" class="text-gray-300 text-center" role="alert">
      <p>{{ failure }}</p><button @click.stop="retry" class="mt-4 text-blue-400">重试</button>
    </div>
    <template v-else-if="item.media_type === 'video'">
      <div class="relative max-w-full max-h-[calc(100vh-2rem)]">
        <video
          ref="videoEl"
          :key="retryKey"
          :src="getStreamUrl(item.id)"
          autoplay
          class="max-w-full max-h-[calc(100vh-2rem)] rounded-lg"
          @click.stop="videoEl && (videoEl.paused ? videoEl.play() : videoEl.pause())"
          @pause="videoPaused = true"
          @play="videoPaused = false"
          @error="onError"
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
      :key="retryKey"
      :src="getStreamUrl(item.id)"
      class="max-w-full max-h-full object-contain rounded-lg cursor-pointer"
      @click="closePlayer"
      @error="onError"
    />
  </div>
</template>
