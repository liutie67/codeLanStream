export type MediaType = 'video' | 'image'
export type ExportTag = 'favorited' | 'deleted' | 'damaged'
export type Availability = 'available' | 'missing' | 'unavailable'
export type AvailabilityFilter = Availability | 'all'

export interface PurgeFailure {
  media_id: string
  file_path: string
  error: string
}

export interface PurgeResponse {
  deleted_count: number
  failed_count: number
  failures: PurgeFailure[]
  unprocessed_count: number
}

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
  is_damaged: boolean
  availability: Availability
  availability_checked_at: string | null
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
  availability: Availability
}

export interface AvailabilityJob {
  id: string
  status: 'queued' | 'running' | 'cancelling' | 'completed' | 'cancelled' | 'interrupted' | 'failed'
  message: string
  processed: number
  total: number
  available: number
  missing: number
  unavailable: number
  percent: number
  error: string | null
  created_at: string
  updated_at: string
}

export interface BrowseResponse {
  roots: BrowseRoot[]
  folders: string[]
  items: MediaItem[]
  total: number
  page: number
  page_size: number
  has_next: boolean
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
  request_id?: string
  path: string
  preview: boolean
  media_type?: MediaType | null
  recursive: boolean
  skip_hidden: boolean
  backfill_existing: boolean
  workers?: number | null
}

export interface ImportTargetInfo {
  path: string
  is_existing_library_path: boolean
  existing_count: number
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

export type ImportJobStatus = 'queued' | 'running' | 'cancelling' | 'completed' | 'failed' | 'cancelled' | 'interrupted'

export type ImportJobStage =
  | 'queued'
  | 'preparing'
  | 'scanning'
  | 'thumbnail'
  | 'preview'
  | 'committing'
  | 'cancelling'
  | 'cancelled'
  | 'interrupted'
  | 'completed'
  | 'failed'

export interface ImportJobProgress {
  id: string
  request_id: string | null
  options: ImportMediaRequest
  status: ImportJobStatus
  stage: ImportJobStage
  message: string
  percent: number
  current: number
  total: number
  current_file: string | null
  stats: ImportMediaResponse
  error: string | null
  created_at: string
  updated_at: string
}
