export type Asset = {
  id: string
  role: 'character' | 'reference'
  filename: string
  kind: 'image' | 'video'
  size: number
  width?: number
  height?: number
  duration?: number | null
  file_url: string
  fps?: number | null
  has_audio?: boolean
  review_status: 'pending' | 'approved' | 'rejected'
  created_at: string
  analysis?: Record<string, unknown>
  thumbnail_url?: string
}

export type JobStatus = 'queued' | 'preparing' | 'submitting' | 'running' | 'validating' | 'completed' | 'failed' | 'cancelled'
export type Job = {
  id: string
  status: JobStatus
  created_at: string
  updated_at?: string
  character_id: string
  reference_id: string
  progress?: number | null
  stage?: string | null
  message?: string | null
  error?: string | null
  output_url?: string | null
  result_url?: string | null
  thumbnail_url?: string | null
  settings?: GenerationSettings
  logs?: { message: string; time?: string }[]
  quality_report?: Record<string, unknown> | null
}

export type GenerationSettings = {
  quality: string
  model_version: 'v3' | 'v2.6'
  character_orientation: string
  keep_original_sound: boolean
  prompt: string
  duration: number
  output_fps: number
  trim_start: number
}

export type LocalEngineStatus = {
  configured: boolean
  ready: boolean
  issues: string[]
  gpu: { available: boolean; name: string | null; vram_gb: number | null }
}

export type LocalEngineSettings = LocalEngineStatus & {
  url: string
  model: string
}

export type Capabilities = {
  app_name?: string
  desktop_mode?: boolean
  provider: { id: string; label: string; configured: boolean; model: string; reason?: string | null }
  local?: LocalEngineStatus
  review: { configured: boolean; required: boolean; desktop_owner?: boolean }
  limits: { image_mb: number; video_mb: number; min_duration: number; max_duration_video: number; max_duration_image: number }
  features: { character_video_mode: string; pose_estimation: boolean; identity_verification: boolean; motion_intensity: boolean; face_preservation_control: boolean }
  auth_required: boolean
}
