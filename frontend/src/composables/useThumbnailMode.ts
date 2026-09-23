import { ref, watch } from 'vue'

type ThumbnailMode = 'first-frame' | 'grid'

const mode = ref<ThumbnailMode>(
  (localStorage.getItem('lanstream-thumb-mode') as ThumbnailMode) || 'first-frame'
)

watch(mode, (val) => {
  localStorage.setItem('lanstream-thumb-mode', val)
})

export function useThumbnailMode() {
  function toggleMode() {
    mode.value = mode.value === 'first-frame' ? 'grid' : 'first-frame'
  }
  return { thumbMode: mode, toggleMode }
}
