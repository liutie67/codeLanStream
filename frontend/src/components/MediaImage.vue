<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { MediaItem } from '../api/types'
import { getStreamUrl, getThumbnailUrl, getPreviewUrl, recheckMedia } from '../api/client'
import { useThumbnailMode } from '../composables/useThumbnailMode'

const props = defineProps<{ item: MediaItem; compact?: boolean }>()
const emit = defineEmits<{ unavailable: [id: string] }>()
const { thumbMode } = useThumbnailMode()
const failed = ref(false)
const fallback = ref(false)
const message = ref('媒体加载失败')
let version = 0
let checked = false
watch([() => props.item.id, thumbMode], () => {
  version++
  failed.value = false
  fallback.value = false
  checked = false
  message.value = '媒体加载失败'
})
const src = computed(() => {
  if (props.item.media_type === 'image') return getStreamUrl(props.item.id)
  if (fallback.value || thumbMode.value !== 'grid') return props.item.thumbnail_path ? getThumbnailUrl(props.item.id) : ''
  return props.item.preview_path ? getPreviewUrl(props.item.id) : ''
})
async function onError() {
  const item = props.item
  const token = version
  if (item.media_type === 'video' && thumbMode.value === 'grid' && !fallback.value && item.thumbnail_path) fallback.value = true
  else failed.value = true
  if (checked) return
  checked = true
  try {
    const [result] = await recheckMedia([item.id])
    if (token !== version) return
    if (!result || result.availability !== 'available') emit('unavailable', item.id)
  } catch {
    message.value = '加载失败，请检查硬盘或网络'
  }
}
</script>

<template>
  <div>
    <img v-if="src && !failed" :src="src" :alt="item.file_path.split(/[/\\]/).pop()"
      :class="['w-full block', compact ? 'h-full object-cover rounded' : '']" loading="lazy" decoding="async" @error="onError" />
    <div v-else class="w-full h-full min-h-12 bg-black/80 flex items-center justify-center rounded text-gray-300" :style="compact ? '' : 'aspect-ratio: 16/9'">
      <span :class="compact ? 'text-[9px] text-center px-1' : 'text-xs text-center px-2'">{{ failed ? message : '还未生成对应缩略图' }}</span>
    </div>
  </div>
</template>
