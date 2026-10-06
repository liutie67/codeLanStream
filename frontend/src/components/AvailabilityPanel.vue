<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'
import type { AvailabilityJob } from '../api/types'
import { cancelAvailabilityCheck, fetchAvailabilityChecks, recheckMedia, removeMediaRecords, startAvailabilityCheck } from '../api/client'

const props = defineProps<{ selectedIds: string[]; invalidIds: string[] }>()
const emit = defineEmits<{ changed: [] }>()
const job = ref<AvailabilityJob | null>(null)
const busy = ref(false)
const message = ref('')
const active = computed(() => !!job.value && ['queued', 'running', 'cancelling'].includes(job.value.status))
let timer: ReturnType<typeof setTimeout> | undefined
let disposed = false
let controller: AbortController | undefined
let announced = ''
let epoch = 0

async function discover() {
  const token = ++epoch
  controller?.abort()
  clearTimeout(timer)
  controller = new AbortController()
  try {
    const records = await fetchAvailabilityChecks(controller.signal)
    if (disposed || token !== epoch) return
    job.value = records.find(item => ['queued', 'running', 'cancelling'].includes(item.status)) || records[0] || null
    if (job.value && !active.value && announced !== `${job.value.id}:${job.value.status}`) {
      announced = `${job.value.id}:${job.value.status}`
      emit('changed')
    }
  } catch (error) {
    if (!disposed && token === epoch) message.value = error instanceof Error ? error.message : '检查状态读取失败'
  } finally {
    if (!disposed && token === epoch) timer = setTimeout(() => void discover(), active.value ? 1000 : 5000)
  }
}
async function startCheck() {
  busy.value = true
  message.value = ''
  try { job.value = await startAvailabilityCheck(); void discover() }
  catch (error) { message.value = error instanceof Error ? error.message : '检查启动失败' }
  finally { busy.value = false }
}
async function cancelCheck() {
  if (!job.value) return
  try { job.value = await cancelAvailabilityCheck(job.value.id) }
  catch (error) { message.value = error instanceof Error ? error.message : '取消失败' }
}
async function selectionAction(remove = false) {
  const ids = [...(remove ? props.invalidIds : props.selectedIds)]
  if (!ids.length) return
  if (remove && !confirm(`移除 ${ids.length} 条失效索引？这些记录的收藏、删除和损坏分类会丢失。原文件不会被删除。`)) return
  busy.value = true
  message.value = ''
  let completed = 0
  try {
    for (let offset = 0; offset < ids.length; offset += 200) {
      const batch = ids.slice(offset, offset + 200)
      if (remove) completed += (await removeMediaRecords(batch)).removed_count
      else completed += (await recheckMedia(batch)).length
    }
    message.value = remove ? `已移除 ${completed} 条索引，原文件保留` : `已复查 ${completed} 条记录`
  } catch (error) { message.value = `${error instanceof Error ? error.message : '操作失败'}${completed ? `（已处理 ${completed} 条）` : ''}` }
  finally { busy.value = false; emit('changed') }
}
onMounted(() => void discover())
onUnmounted(() => { disposed = true; clearTimeout(timer); controller?.abort() })
</script>

<template>
  <section class="mb-5 p-4 rounded-xl border border-gray-500/30" aria-label="媒体来源检查">
    <div class="flex flex-wrap items-center gap-3 text-sm">
      <span class="font-medium">媒体来源检查</span>
      <button :disabled="busy || active" @click="startCheck" class="px-3 py-1.5 rounded bg-blue-600/20 text-blue-400 disabled:opacity-40">检查全库</button>
      <button :disabled="busy || !selectedIds.length" @click="selectionAction()" class="px-3 py-1.5 rounded bg-gray-500/20 disabled:opacity-40">复查选中 ({{ selectedIds.length }})</button>
      <button :disabled="busy || !invalidIds.length" @click="selectionAction(true)" class="px-3 py-1.5 rounded bg-amber-600/20 text-amber-500 disabled:opacity-40">移除失效索引 ({{ invalidIds.length }})</button>
      <button v-if="active" :disabled="job?.status === 'cancelling'" @click="cancelCheck" class="text-amber-500 disabled:opacity-40">取消检查</button>
    </div>
    <div v-if="job" class="mt-3 text-xs text-gray-500" aria-live="polite">
      <p>{{ job.message }} · {{ job.processed }} / {{ job.total }} · 可用 {{ job.available }} · 缺失 {{ job.missing }} · 暂不可访问 {{ job.unavailable }}</p>
      <progress v-if="active" :value="job.percent" max="100" class="w-full mt-2 h-2" />
      <p v-if="job.error" class="mt-1 text-red-400">{{ job.error }}</p>
    </div>
    <p v-if="message" class="mt-2 text-xs text-amber-500" role="status">{{ message }}</p>
    <p class="mt-2 text-xs text-gray-500">失效记录保留原有分类。检查在后台运行，离开页面后仍会继续。</p>
  </section>
</template>
