import type { BrowseResponse, FeedResponse, MediaItem, RandomResponse } from './types'

const API_BASE = '/api/media'

export async function fetchFeed(params: {
  page?: number
  page_size?: number
  media_type?: string
  folder?: string
  is_favorited?: boolean
  is_deleted?: boolean
}): Promise<FeedResponse> {
  const search = new URLSearchParams()
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  if (params.media_type) search.set('media_type', params.media_type)
  if (params.folder) search.set('folder', params.folder)
  if (params.is_favorited !== undefined) search.set('is_favorited', String(params.is_favorited))
  if (params.is_deleted !== undefined) search.set('is_deleted', String(params.is_deleted))

  const res = await fetch(`${API_BASE}/feed?${search}`)
  return res.json()
}

export async function fetchRandom(
  count: number = 50,
  excludeIds: string[] = [],
  mediaType?: string | null,
  isFavorited?: boolean | null,
  isDeleted?: boolean | null,
): Promise<RandomResponse> {
  const search = new URLSearchParams()
  search.set('count', String(count))
  if (excludeIds.length > 0) search.set('exclude_ids', excludeIds.join(','))
  if (mediaType) search.set('media_type', mediaType)
  if (isFavorited !== undefined && isFavorited !== null) search.set('is_favorited', String(isFavorited))
  if (isDeleted !== undefined && isDeleted !== null) search.set('is_deleted', String(isDeleted))
  const res = await fetch(`${API_BASE}/random?${search}`)
  return res.json()
}

export async function fetchBrowse(rootDir?: string, subdir?: string, mediaType?: string | null): Promise<BrowseResponse> {
  const search = new URLSearchParams()
  if (rootDir) search.set('root_dir', rootDir)
  if (subdir) search.set('subdir', subdir)
  if (mediaType) search.set('media_type', mediaType)
  const res = await fetch(`${API_BASE}/browse?${search}`)
  return res.json()
}

export function getStreamUrl(mediaId: string): string {
  return `${API_BASE}/stream/${mediaId}`
}

export function getThumbnailUrl(mediaId: string): string {
  return `${API_BASE}/thumbnail/${mediaId}`
}

export async function toggleFavorite(id: string): Promise<MediaItem> {
  const res = await fetch(`${API_BASE}/${id}/favorite`, { method: 'POST' })
  return res.json()
}

export async function toggleDelete(id: string): Promise<MediaItem> {
  const res = await fetch(`${API_BASE}/${id}/delete`, { method: 'POST' })
  return res.json()
}

export async function purgeDeleted(): Promise<{ deleted_count: number }> {
  const res = await fetch(`${API_BASE}/manage/purge`, { method: 'POST' })
  return res.json()
}

export async function exportFavorites(targetDir: string): Promise<{ exported_count: number }> {
  const res = await fetch(`${API_BASE}/manage/export-favorites`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_dir: targetDir }),
  })
  return res.json()
}

export async function batchUpdate(ids: string[], action: string): Promise<{ updated_count: number }> {
  const res = await fetch(`${API_BASE}/manage/batch`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ ids, action }),
  })
  return res.json()
}
