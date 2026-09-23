<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import ImportMediaDialog from './components/ImportMediaDialog.vue'
import { useImportTask } from './composables/useImportTask'

const task = useImportTask()
const { visible, locked, activeJob, recentJobs } = task
const historyOpen = ref(false)
const router = useRouter()
const removeGuard = router.beforeEach(() => !locked.value)
function beforeUnload(event: BeforeUnloadEvent) {
  event.preventDefault()
  event.returnValue = ''
}
watch(locked, value => {
  if (value) window.addEventListener('beforeunload', beforeUnload)
  else window.removeEventListener('beforeunload', beforeUnload)
})
function onVisible() {
  if (document.visibilityState === 'visible') {
    void task.discover()
    task.retry()
  }
}
onMounted(() => {
  task.initialize()
  document.addEventListener('visibilitychange', onVisible)
})
onUnmounted(() => {
  removeGuard()
  task.dispose()
  document.removeEventListener('visibilitychange', onVisible)
  window.removeEventListener('beforeunload', beforeUnload)
})
</script>

<template>
  <div :inert="visible || undefined">
    <RouterView />
    <div v-if="activeJob || recentJobs.length" class="fixed bottom-4 right-4 z-[65] flex flex-col items-end gap-2">
      <div v-if="historyOpen" class="max-h-72 w-80 overflow-auto rounded-xl border border-gray-600 bg-gray-900 p-3 text-white shadow-xl">
        <p class="mb-2 text-sm font-semibold">最近导入任务</p>
        <button v-for="item in recentJobs" :key="item.id" class="block w-full rounded-lg p-2 text-left hover:bg-gray-800"
          @click="historyOpen = false; task.track(item)">
          <span class="block truncate text-xs">{{ item.stats.root_dir }}</span>
          <span class="text-xs text-gray-400">{{ item.message }} · 已保存 {{ item.stats.added_count }} 项</span>
        </button>
      </div>
      <button v-if="activeJob" class="rounded-full bg-blue-600 px-4 py-2 text-sm text-white shadow-lg" @click="task.track(activeJob)">
        {{ activeJob.status === 'cancelling' ? '正在安全终止' : '正在导入' }} · {{ activeJob.percent }}% · 查看进度
      </button>
      <button v-if="recentJobs.length" class="rounded-full bg-gray-800 px-3 py-1.5 text-xs text-white shadow-lg" @click="historyOpen = !historyOpen">导入记录</button>
    </div>
  </div>
  <ImportMediaDialog v-if="visible" />
</template>
