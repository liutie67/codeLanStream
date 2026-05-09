<script setup lang="ts">
defineProps<{ loading: boolean; hasMore: boolean }>()
const emit = defineEmits<{ load: [] }>()
</script>

<template>
  <div class="py-8 text-center">
    <div v-if="loading" class="text-gray-400">
      <span class="inline-block animate-spin mr-2">&#9696;</span> 加载中...
    </div>
    <button
      v-else-if="hasMore"
      @click="emit('load')"
      class="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors"
    >
      加载更多
    </button>
    <p v-else class="text-gray-400">已加载全部</p>
  </div>
</template>
