import type { Role } from '@/types/auth'

export type RangeParam = '1h' | '24h' | '7d'
export type Granularity = 'minute' | 'hour'
export type SortOrder = 'asc' | 'desc'

export interface Page<T> {
  items: T[]
  total: number
  limit: number
  offset: number
}

export interface SummaryResponse {
  range: RangeParam | null
  since: string
  until: string
  total_requests: number
  blocked_requests: number
  allowed_requests: number
  active_client_count: number
  active_user_count: number
}

export interface TimeseriesPoint {
  bucket_ts: string
  total_requests: number
  blocked_requests: number
  allowed_requests: number
}

export interface TimeseriesResponse {
  granularity: Granularity
  points: TimeseriesPoint[]
}

export interface DomainStat {
  domain: string
  request_count: number
  blocked_count: number
  total_bytes: number
  category: DomainCategoryLabel
}

export interface DomainStatsResponse {
  items: DomainStat[]
}

export type DomainCategoryLabel =
  | 'uncategorized'
  | 'social_media'
  | 'video_streaming'
  | 'music_streaming'
  | 'gaming'
  | 'work_tools'
  | 'shopping'
  | 'news'
  | 'gambling'
  | 'adult_content'
  | 'other'

export interface DomainCategoryOut {
  domain: string
  category: DomainCategoryLabel
  updated_at: string
}

export interface CategoryStat {
  category: DomainCategoryLabel
  request_count: number
  blocked_count: number
  total_bytes: number
}

export interface CategoryStatsResponse {
  items: CategoryStat[]
}

export interface Branch {
  slug: string
  label: string
}

export interface BranchesResponse {
  items: Branch[]
}

export interface AlertSettingsOut {
  branch: string
  sensitive_categories: DomainCategoryLabel[]
  non_work_minutes_threshold: number
  client_daily_byte_quota_bytes: number | null
  uncategorized_domain_request_threshold: number | null
  updated_at: string
}

export interface ReportStatus {
  schedule: 'disabled' | 'daily' | 'weekly'
  recipients_configured: boolean
  smtp_configured: boolean
  last_sent_at: string | null
}

export interface ClientSummary {
  client_ip: string
  user: string | null
  branch: string | null
  total_requests: number
  blocked_requests: number
  total_bytes: number
  last_activity: string | null
}

export interface LogSourceHealth {
  branch: string
  alive: boolean
  lines_seen: number
  lines_parsed: number
  parse_failure_rate: number | null
}

export interface HealthResponse {
  status: string
  time: string
  log_tailer_alive: boolean
  log_lines_seen: number
  log_lines_parsed: number
  log_parse_failure_rate: number | null
  log_sources: LogSourceHealth[]
  unarchived_purge_branches: string[]
}

export interface DomainSummary {
  domain: string
  total_requests: number
  blocked_requests: number
  total_bytes: number
  distinct_client_count: number
  category: DomainCategoryLabel
}

export interface DomainClientStat {
  client_ip: string
  user: string | null
  visit_count: number
  blocked_count: number
  total_bytes: number
  last_visit: string | null
}


export interface UserSummary {
  id: string
  email: string
  role: Role
  branch: string | null
  created_at: string
}

export type AuditAction =
  | 'user_created'
  | 'user_role_changed'
  | 'user_password_reset'
  | 'user_deleted'
  | 'export_created'
  | 'export_downloaded'

export interface AuditLogEntry {
  id: string
  created_at: string
  action: AuditAction
  actor_email: string
  target_email: string | null
  detail: string | null
}

export type AnomalySeverity = 'low' | 'medium' | 'high' | 'critical'

export interface AnomalyEvent {
  id: string
  generated_at: string
  title: string
  description: string
  severity: AnomalySeverity
  client_ip: string | null
  domain: string | null
  branch: string
  kind: string | null
  params: Record<string, string | number> | null
}

export type ExportJobStatus = 'pending' | 'running' | 'done' | 'failed' | 'cancelled'

export interface ExportJob {
  id: string
  status: ExportJobStatus
  format: string
  since: string
  until: string
  blocked_only: boolean
  branch: string | null
  domain: string | null
  category: string | null
  client_ip: string | null
  columns: string[] | null
  row_count: number | null
  file_size_bytes: number | null
  checksum_sha256: string | null
  error_message: string | null
  created_at: string
  completed_at: string | null
  share_link_active: boolean
  share_link_expires_at: string | null
}

export interface ExportShareLink {
  token: string
  expires_at: string
  download_url: string
}

export type ExportCleanupMode = 'time_based' | 'after_download'

export interface ExportSettingsOut {
  cleanup_mode: ExportCleanupMode
  retention_hours: number
  warn_undownloaded_after_hours: number | null
  updated_at: string
}
