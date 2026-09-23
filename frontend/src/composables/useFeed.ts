import { ref } from 'vue'
import type { MediaItem, MediaType } from '../api/types'
import { fetchRandom } from '../api/client'

const FEED_BATCH_SIZE = 80

export function useFeed() {
  const items = ref<MediaItem[]>([])
  const loading = ref(false)
  const hasMore = ref(true)
  const total = ref(0)
  const mediaType = ref<MediaType | null>(null)
  const loadedIds = ref<Set<string>>(new Set())

  async function loadMore() {
    if (loading.value || !hasMore.value) return
    loading.value = true
    try {
      const res = await fetchRandom(FEED_BATCH_SIZE, [...loadedIds.value], mediaType.value)
      for (const item of res.items) {
        loadedIds.value.add(item.id)
      }
      items.value.push(...res.items)
      total.value = res.total
      if (res.items.length < FEED_BATCH_SIZE) hasMore.value = false
    } finally {
      loading.value = false
    }
  }

  async function refresh() {
    items.value = []
    loadedIds.value = new Set()
    hasMore.value = true
    await loadMore()
  }

  function setMediaType(type: MediaType | null) {
    mediaType.value = type
    refresh()
  }

  loadMore()

  return { items, loading, hasMore, total, mediaType, loadMore, refresh, setMediaType }
}
