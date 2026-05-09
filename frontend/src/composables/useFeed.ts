import { ref } from 'vue'
import type { MediaItem, MediaType } from '../api/types'
import { fetchFeed } from '../api/client'

export function useFeed() {
  const items = ref<MediaItem[]>([])
  const loading = ref(false)
  const page = ref(1)
  const hasMore = ref(true)
  const total = ref(0)
  const mediaType = ref<MediaType | null>(null)

  async function loadMore() {
    if (loading.value || !hasMore.value) return
    loading.value = true
    try {
      const res = await fetchFeed({
        page: page.value,
        media_type: mediaType.value ?? undefined,
      })
      items.value.push(...res.items)
      total.value = res.total
      hasMore.value = res.has_next
      page.value++
    } finally {
      loading.value = false
    }
  }

  function setMediaType(type: MediaType | null) {
    mediaType.value = type
    items.value = []
    page.value = 1
    hasMore.value = true
    loadMore()
  }

  // 首次加载
  loadMore()

  return { items, loading, hasMore, total, mediaType, loadMore, setMediaType }
}
