<script setup lang="ts">
import { ref, watch, onUnmounted } from 'vue'

const props = defineProps<{ video: HTMLVideoElement | null; tallBar?: boolean }>()

const barRef = ref<HTMLElement>()
const volBarRef = ref<HTMLElement>()
const pct = ref(0)
const vol = ref(1)
const muted = ref(true)
const curTime = ref(0)
const dur = ref(0)
const dragProgress = ref(false)
const dragVolume = ref(false)
let seekBaseX = 0
let seekBaseTime = 0
let seekMoved = false

function sync() {
  const v = props.video
  if (!v) return
  if (!dragProgress.value) {
    pct.value = v.duration ? (v.currentTime / v.duration) * 100 : 0
    curTime.value = v.currentTime
    dur.value = v.duration || 0
  }
  if (!dragVolume.value) {
    vol.value = v.volume
    muted.value = v.muted
  }
}

function volFromEvent(e: PointerEvent) {
  const v = props.video, b = volBarRef.value
  if (!v || !b) return
  const rect = b.getBoundingClientRect()
  const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
  v.volume = ratio
  v.muted = ratio === 0
  vol.value = ratio
  muted.value = ratio === 0
}

function toggleMute() {
  const v = props.video
  if (!v) return
  if (v.muted || v.volume === 0) {
    v.muted = false
    v.volume = vol.value || 0.5
  } else {
    v.muted = true
  }
}

function goFullscreen() {
  const v = props.video
  if (!v) return
  if (document.fullscreenElement) {
    document.exitFullscreen()
    return
  }
  if ((v as any).webkitEnterFullscreen) {
    ;(v as any).webkitEnterFullscreen()
    return
  }
  v.requestFullscreen?.()
}

function onProgressDown(e: PointerEvent) {
  dragProgress.value = true
  seekMoved = false
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  seekBaseX = e.clientX
  const v = props.video
  seekBaseTime = v && v.duration ? v.currentTime : 0
}

function onProgressMove(e: PointerEvent) {
  if (!dragProgress.value) return
  if (Math.abs(e.clientX - seekBaseX) > 3) seekMoved = true
  if (!seekMoved) return
  const v = props.video, b = barRef.value
  if (!v || !b || !v.duration) return
  const rect = b.getBoundingClientRect()
  const delta = (e.clientX - seekBaseX) / rect.width * v.duration
  const t = Math.max(0, Math.min(v.duration, seekBaseTime + delta))
  v.currentTime = t
  pct.value = (t / v.duration) * 100
  curTime.value = t
}
function onVolDown(e: PointerEvent) {
  dragVolume.value = true
  ;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)
  volFromEvent(e)
}
function onVolMove(e: PointerEvent) { if (dragVolume.value) volFromEvent(e) }
function onUp(e: PointerEvent) {
  if (dragProgress.value && !seekMoved) {
    const v = props.video, b = barRef.value
    if (v && b && v.duration) {
      const rect = b.getBoundingClientRect()
      const ratio = Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width))
      v.currentTime = ratio * v.duration
      pct.value = ratio * 100
      curTime.value = v.currentTime
    }
  }
  dragProgress.value = false
  dragVolume.value = false
}

function fmt(s: number): string {
  if (!s || !isFinite(s)) return '0:00'
  const m = Math.floor(s / 60)
  const sec = Math.floor(s % 60)
  return `${m}:${sec.toString().padStart(2, '0')}`
}

let raf = 0
function loop() { sync(); raf = requestAnimationFrame(loop) }

watch(() => props.video, v => {
  cancelAnimationFrame(raf)
  if (v) loop()
}, { immediate: true })

onUnmounted(() => cancelAnimationFrame(raf))
</script>

<template>
  <div :class="['select-none pt-3', tallBar ? 'flex flex-col flex-1' : '']" style="touch-action: none" @pointerdown.stop @click.stop @touchstart.stop>
    <!-- Progress bar — tall touch target for mobile -->
    <div
      ref="barRef"
      :class="['relative flex items-center cursor-pointer', tallBar ? 'flex-1' : 'h-10']"
      @pointerdown="onProgressDown"
      @pointermove="onProgressMove"
      @pointerup="onUp"
      @pointercancel="onUp"
    >
      <div class="h-[3px] hover:h-[5px] w-full bg-white/20 rounded-full relative transition-[height]">
        <div class="absolute inset-y-0 left-0 bg-white rounded-full" :style="{ width: pct + '%' }" />
      </div>
    </div>
    <!-- Volume + Time -->
    <div class="flex items-center gap-2 h-6">
      <button @click="toggleMute" class="text-white/60 hover:text-white transition-colors shrink-0">
        <svg v-if="muted" class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
          <path stroke-linecap="round" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
        </svg>
        <svg v-else-if="vol < 0.5" class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
          <path d="M15.536 8.464a5 5 0 010 7.072" />
        </svg>
        <svg v-else class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
          <path d="M15.536 8.464a5 5 0 010 7.072M18.364 5.636a9 9 0 010 12.728" />
        </svg>
      </button>
      <div
        ref="volBarRef"
        class="w-16 h-4 flex items-center cursor-pointer shrink-0"
        @pointerdown="onVolDown"
        @pointermove="onVolMove"
        @pointerup="onUp"
        @pointercancel="onUp"
      >
        <div class="h-[2px] w-full bg-white/20 rounded-full relative">
          <div class="absolute inset-y-0 left-0 bg-white/60 rounded-full" :style="{ width: (muted ? 0 : vol * 100) + '%' }" />
        </div>
      </div>
      <span class="text-[10px] text-white/40 tabular-nums ml-auto">{{ fmt(curTime) }} / {{ fmt(dur) }}</span>
      <button @click="goFullscreen" class="text-white/60 hover:text-white transition-colors shrink-0">
        <svg class="w-4 h-4" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" d="M3.75 3.75v4.5m0-4.5h4.5m-4.5 0L9 9M3.75 20.25v-4.5m0 4.5h4.5m-4.5 0L9 15M20.25 3.75h-4.5m4.5 0v4.5m0-4.5L15 9m5.25 11.25h-4.5m4.5 0v-4.5m0 4.5L15 15" />
        </svg>
      </button>
    </div>
  </div>
</template>
