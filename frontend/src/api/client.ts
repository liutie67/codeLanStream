import type { FeedResponse, MediaItem } from './types'

const API_BASE = '/api/media'

export async function fetchFeed(params: {
  page?: number
  page_size?: number
  media_type?: string
  folder?: string
}): Promise<FeedResponse> {
  const search = new URLSearchParams()
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  if (params.media_type) search.set('media_type', params.media_type)
  if (params.folder) search.set('folder', params.folder)

  const res = await fetch(`${API_BASE}/feed?${search}`)
  return res.json()
}

export async function fetchRandom(count: number = 10): Promise<MediaItem[]> {
  const res = await fetch(`${API_BASE}/random?count=${count}`)
  return res.json()
}

export function getStreamUrl(mediaId: string): string {
  return `${API_BASE}/stream/${mediaId}`
}

export function getThumbnailUrl(mediaId: string): string {
  return `${API_BASE}/thumbnail/${mediaId}`
}
