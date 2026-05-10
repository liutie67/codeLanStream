export type MediaType = 'video' | 'image'

export interface MediaItem {
  id: string
  file_path: string
  media_type: MediaType
  size_bytes: number
  duration: number | null
  width: number | null
  height: number | null
  folder: string | null
  root_dir: string | null
  thumbnail_path: string | null
  is_favorited: boolean
  is_deleted: boolean
  created_at: string
}

export interface FeedResponse {
  items: MediaItem[]
  total: number
  page: number
  page_size: number
  has_next: boolean
}

export interface RandomResponse {
  items: MediaItem[]
  total: number
}

export interface BrowseRoot {
  path: string
  name: string
  count: number
}

export interface BrowseResponse {
  roots: BrowseRoot[]
  folders: string[]
  items: MediaItem[]
}
