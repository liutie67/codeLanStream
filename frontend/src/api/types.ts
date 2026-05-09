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
  thumbnail_path: string | null
  created_at: string
}

export interface FeedResponse {
  items: MediaItem[]
  total: number
  page: number
  page_size: number
  has_next: boolean
}
