<script setup lang="ts">
import type { MediaType } from '../api/types'

defineProps<{ current: MediaType | null }>()
const emit = defineEmits<{
  change: [type: MediaType | null]
}>()

type FilterOption = { label: string; value: MediaType | null }
const filters: FilterOption[] = [
  { label: '全部', value: null },
  { label: '视频', value: 'video' },
  { label: '图片', value: 'image' },
]
</script>

<template>
  <div class="flex gap-2">
    <button
      v-for="f in filters"
      :key="f.label"
      @click="emit('change', f.value)"
      :class="[
        'px-4 py-1.5 rounded-full text-sm font-medium transition-colors',
        current === f.value
          ? 'bg-blue-600 text-white'
          : 'bg-gray-100 text-gray-700 hover:bg-gray-200',
      ]"
    >
      {{ f.label }}
    </button>
  </div>
</template>
