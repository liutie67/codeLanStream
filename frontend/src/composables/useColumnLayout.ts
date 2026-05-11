import { ref, watch, type Ref } from 'vue'
import type { MediaItem } from '../api/types'

export function useColumnLayout(items: Ref<MediaItem[]>, colCount: Ref<number>) {
  const columns = ref<MediaItem[][]>([])
  let prevLen = 0

  function distribute() {
    const n = colCount.value
    const cols: MediaItem[][] = Array.from({ length: n }, () => [])
    for (const item of items.value) {
      const shortest = cols.reduce((min, col, i) =>
        col.length < cols[min].length ? i : min, 0)
      cols[shortest].push(item)
    }
    columns.value = cols
    prevLen = items.value.length
  }

  function append() {
    const newItems = items.value.slice(prevLen)
    if (newItems.length === 0) return
    const cols = [...columns.value]
    for (const item of newItems) {
      const shortest = cols.reduce((min, col, i) =>
        col.length < cols[min].length ? i : min, 0)
      cols[shortest] = [...cols[shortest], item]
    }
    columns.value = cols
    prevLen = items.value.length
  }

  watch([() => items.value.length, colCount], ([len], [oldLen]) => {
    if (columns.value.length !== colCount.value || len < (oldLen ?? 0)) {
      distribute()
    } else if (len > (oldLen ?? 0)) {
      append()
    }
  })

  distribute()

  return { columns }
}
