<script setup lang="ts">
import type { MediaType } from '../api/types'
import { useTheme } from '../composables/useTheme'

const { isDark } = useTheme()

defineProps<{ current: MediaType | null }>()
const emit = defineEmits<{
  change: [type: MediaType | null]
}>()

type FilterOption = { label: string; short: string; value: MediaType | null }
const filters: FilterOption[] = [
  { label: '全部', short: '全', value: null },
  { label: '视频', short: '视', value: 'video' },
  { label: '图片', short: '图', value: 'image' },
]
</script>

<template>
  <div :class="['flex rounded-full p-0.5', isDark ? 'bg-gray-800' : 'bg-gray-200']">
    <button
      v-for="f in filters"
      :key="f.label"
      @click="emit('change', f.value)"
      :class="[
        'px-2.5 py-1 rounded-full text-xs font-medium transition-colors',
        'md:px-3 md:text-xs',
        current === f.value
          ? 'bg-blue-600 text-white shadow-sm'
          : isDark ? 'text-gray-400 hover:text-gray-200' : 'text-gray-500 hover:text-gray-700',
      ]"
    >
      <span class="md:hidden">{{ f.short }}</span>
      <span class="hidden md:inline">{{ f.label }}</span>
    </button>
  </div>
</template>
