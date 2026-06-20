import type {
  BrowseResponse,
  DirectoryListResponse,
  FeedResponse,
  ImportJobProgress,
  ImportMediaRequest,
  MediaItem,
  RandomResponse,
  ExportTag,
} from './types'

const API_BASE = '/api/media'

export async function fetchFeed(params: {
  page?: number
  page_size?: number
  media_type?: string
  folder?: string
  folder_exact?: boolean
  folder_after?: string
  sort?: 'created_desc' | 'file_path_asc' | 'size_desc'
  is_favorited?: boolean
  is_deleted?: boolean
  is_damaged?: boolean
}): Promise<FeedResponse> {
  const search = new URLSearchParams()
  if (params.page) search.set('page', String(params.page))
  if (params.page_size) search.set('page_size', String(params.page_size))
  if (params.media_type) search.set('media_type', params.media_type)
  if (params.folder) search.set('folder', params.folder)
  if (params.folder_exact !== undefined) search.set('folder_exact', String(params.folder_exact))
  if (params.folder_after) search.set('folder_after', params.folder_after)
  if (params.sort) search.set('sort', params.sort)
  if (params.is_favorited !== undefined) search.set('is_favorited', String(params.is_favorited))
  if (params.is_deleted !== undefined) search.set('is_deleted', String(params.is_deleted))
  if (params.is_damaged !== undefined) search.set('is_damaged', String(params.is_damaged))

  const res = await fetch(`${API_BASE}/feed?${search}`)
  return res.json()
}

export async function fetchRandom(
  count: number = 50,
  excludeIds: string[] = [],
  mediaType?: string | null,
  isFavorited?: boolean | null,
  isDeleted?: boolean | null,
  isDamaged?: boolean | null,
): Promise<RandomResponse> {
  const res = await fetch(`${API_BASE}/random`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      count,
      exclude_ids: excludeIds,
      ...(mediaType && { media_type: mediaType }),
      ...(isFavorited !== undefined && isFavorited !== null && { is_favorited: isFavorited }),
      ...(isDeleted !== undefined && isDeleted !== null && { is_deleted: isDeleted }),
      ...(isDamaged !== undefined && isDamaged !== null && { is_damaged: isDamaged }),
    }),
  })
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

export function getPreviewUrl(mediaId: string): string {
  return `${API_BASE}/preview/${mediaId}`
}

export async function toggleFavorite(id: string): Promise<MediaItem> {
  const res = await fetch(`${API_BASE}/${id}/favorite`, { method: 'POST' })
  return res.json()
}

export async function toggleDelete(id: string): Promise<MediaItem> {
  const res = await fetch(`${API_BASE}/${id}/delete`, { method: 'POST' })
  return res.json()
}

export async function toggleDamaged(id: string): Promise<MediaItem> {
  const res = await fetch(`${API_BASE}/${id}/damage`, { method: 'POST' })
  return res.json()
}

export async function purgeDeleted(): Promise<{ deleted_count: number }> {
  const res = await fetch(`${API_BASE}/manage/purge`, { method: 'POST' })
  if (!res.ok) throw new Error(`清理失败: ${res.status}`)
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

export async function exportMedia(targetDir: string, tags: ExportTag[]): Promise<{ exported_count: number }> {
  const res = await fetch(`${API_BASE}/manage/export`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ target_dir: targetDir, tags }),
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

export async function fetchDirectories(path?: string): Promise<DirectoryListResponse> {
  const search = new URLSearchParams()
  if (path) search.set('path', path)
  const res = await fetch(`${API_BASE}/manage/directories?${search}`)
  if (!res.ok) {
    let message = `目录读取失败: ${res.status}`
    try {
      const data = await res.json()
      message = data.detail || message
    } catch {
      message = await res.text() || message
    }
    throw new Error(message)
  }
  return res.json()
}

export async function importMediaFolder(body: ImportMediaRequest): Promise<ImportJobProgress> {
  const res = await fetch(`${API_BASE}/manage/import`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    let message = `导入失败: ${res.status}`
    try {
      const data = await res.json()
      message = data.detail || message
    } catch {
      message = await res.text() || message
    }
    throw new Error(message || `导入失败: ${res.status}`)
  }
  return res.json()
}

export async function fetchImportProgress(jobId: string): Promise<ImportJobProgress> {
  const res = await fetch(`${API_BASE}/manage/import/${jobId}`)
  if (!res.ok) {
    let message = `进度读取失败: ${res.status}`
    try {
      const data = await res.json()
      message = data.detail || message
    } catch {
      message = await res.text() || message
    }
    throw new Error(message)
  }
  return res.json()
}
