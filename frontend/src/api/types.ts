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
  preview_path: string | null
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

export interface DirectoryEntry {
  name: string
  path: string
}

export interface DirectoryListResponse {
  path: string
  parent: string | null
  directories: DirectoryEntry[]
}

export interface ImportMediaRequest {
  path: string
  preview: boolean
  media_type?: MediaType | null
  recursive: boolean
  skip_hidden: boolean
  backfill_existing: boolean
  workers?: number | null
}

export interface ImportMediaResponse {
  root_dir: string
  scanned_files: number
  added_count: number
  existing_count: number
  skipped_count: number
  thumbnail_count: number
  preview_count: number
  preview_requested: boolean
}
