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

export interface CacheEfficiencyResponse {
  hit_requests: number
  miss_requests: number
  // null when hit_requests + miss_requests === 0 -- no cacheable traffic in
  // this window, not a real 0% hit rate.
  hit_ratio: number | null
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

export interface DomainCategoryImportError {
  row: number
  domain: string | null
  reason: string
}

export interface DomainCategoryImportResponse {
  applied: number
  errors: DomainCategoryImportError[]
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
  telegram_chat_id: string | null
  updated_at: string
}

export interface TelegramLinkCodeOut {
  code: string
  expires_at: string
}

export interface TelegramLinkStatusOut {
  consumed: boolean
  expired: boolean
  chat_id: string | null
}

export interface TelegramSuperAdminOut {
  chat_id: string | null
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
  branch: string | null
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

// --- Analytics section (/api/analytics/*) ---

export type TrendGranularity = 'hour' | 'day'
export type TrendMetric = 'bytes' | 'requests'
export type RiskBand = 'low' | 'medium' | 'high'
export type RiskSignalKey =
  | 'blocked_ratio'
  | 'sensitive_traffic'
  | 'anomalies'
  | 'quota_breaches'
  | 'uncategorized_domains'

export interface MetricDelta {
  metric: string
  current: number
  previous: number | null
  pct_change: number | null
}

export interface CategoryUsage {
  category: DomainCategoryLabel
  request_count: number
  blocked_count: number
  total_bytes: number
}

export interface DomainUsage {
  domain: string
  request_count: number
  blocked_count: number
  total_bytes: number
  category: DomainCategoryLabel
}

export interface CategoryMover {
  category: DomainCategoryLabel
  current_bytes: number
  previous_bytes: number
  pct_change: number | null
}

export interface AnalyticsOverview {
  since: string
  until: string
  previous_since: string
  previous_until: string
  metrics: MetricDelta[]
  blocked_ratio: number
  cache_hit_ratio: number | null
  top_categories: CategoryUsage[]
  top_domains: DomainUsage[]
  top_blocked_domains: DomainUsage[]
  top_movers: CategoryMover[]
}

export interface CategoryTrendPoint {
  bucket_ts: string
  values: Record<string, number>
}

export interface CategoryTrendResponse {
  granularity: TrendGranularity
  metric: TrendMetric
  categories: DomainCategoryLabel[]
  points: CategoryTrendPoint[]
}

export interface BranchBreakdownRow {
  branch: string
  total_requests: number
  blocked_requests: number
  allowed_requests: number
  total_bytes: number
  blocked_ratio: number
  active_client_count: number
  requests_pct_change: number | null
}

export interface BranchBreakdownResponse {
  rows: BranchBreakdownRow[]
}

export interface RiskSignal {
  key: RiskSignalKey
  raw_value: number
  score: number
  weight: number
}

export interface BranchRiskRow {
  branch: string
  score: number
  band: RiskBand
  signals: RiskSignal[]
  total_requests: number
  blocked_requests: number
  anomaly_count: number
}

export interface BranchRiskResponse {
  since: string
  until: string
  rows: BranchRiskRow[]
}

export interface HeatmapCell {
  weekday: number
  hour: number
  value: number
}

export interface ActivityHeatmapResponse {
  blocked_only: boolean
  /** Minutes east of UTC the weekday/hour split was computed in (0 = UTC). */
  tz_offset_minutes: number
  max_value: number
  cells: HeatmapCell[]
}

// --- Squid operational views (Traffic & cache, Blocks, Who) ---

export interface NamedCount {
  label: string
  request_count: number
  total_bytes: number
  pct: number
}

export interface TimeBucketCounts {
  bucket_ts: string
  values: Record<string, number>
}

export interface ResultCodeResponse {
  granularity: TrendGranularity
  hit_ratio: number | null
  byte_hit_ratio: number | null
  denied_ratio: number
  tunnel_ratio: number
  codes: NamedCount[]
  series_labels: string[]
  series: TimeBucketCounts[]
}

export interface HttpBreakdownResponse {
  methods: NamedCount[]
  status_codes: NamedCount[]
  status_classes: NamedCount[]
  denied_403: number
  proxy_auth_407: number
  server_error_5xx: number
}

export interface HierarchyResponse {
  codes: NamedCount[]
}

export interface ResponseTimePoint {
  bucket_ts: string
  p50: number
  p95: number
  p99: number
  mean: number
  request_count: number
}

export interface ResponseTimeResponse {
  granularity: TrendGranularity
  overall_p50: number
  overall_p95: number
  overall_p99: number
  overall_mean: number
  sample_count: number
  bands: NamedCount[]
  series: ResponseTimePoint[]
}

export interface ActorRow {
  actor: string
  is_user: boolean
  request_count: number
  blocked_count: number
  blocked_ratio: number
  total_bytes: number
  top_category: DomainCategoryLabel | null
}

export interface ActorLeaderboardResponse {
  actor_kind: string
  rows: ActorRow[]
}

export interface ActorCategorySlice {
  category: DomainCategoryLabel
  request_count: number
  total_bytes: number
}

export interface ActorDomainRow {
  domain: string
  request_count: number
  blocked_count: number
  total_bytes: number
}

export interface ActorDetailResponse {
  actor: string
  is_user: boolean
  first_seen: string | null
  last_seen: string | null
  request_count: number
  blocked_count: number
  total_bytes: number
  categories: ActorCategorySlice[]
  top_domains: ActorDomainRow[]
  denied_domains: ActorDomainRow[]
  hourly: number[]
}

export interface NewEntitiesResponse {
  since: string
  until: string
  new_users: string[]
  new_clients: string[]
  new_users_total: number
  new_clients_total: number
}

export interface DenialReasonPoint {
  bucket_ts: string
  acl_denied: number
  proxy_auth: number
  other_blocked: number
}

export interface DenialsResponse {
  granularity: TrendGranularity
  total_denied: number
  acl_denied: number
  proxy_auth: number
  other_blocked: number
  series: DenialReasonPoint[]
  top_domains: ActorDomainRow[]
  top_categories: ActorCategorySlice[]
  top_actors: ActorRow[]
}

export interface BranchIngestRow {
  branch: string
  tailer_alive: boolean
  parse_failure_rate: number | null
  lines_seen: number
  lines_parsed: number
}

export interface IngestHealthResponse {
  aggregator_backlog_ratio: number
  aggregator_events_likely_lost: boolean
  branches: BranchIngestRow[]
}

export type ConfigFindingCode =
  | 'no_caching'
  | 'no_proxy_auth'
  | 'no_denies'
  | 'sensitive_allowed'
  | 'single_domain_dominant'

export interface ConfigFinding {
  code: ConfigFindingCode
  severity: 'info' | 'warning'
  value: number
  detail: string | null
}

export interface ConfigAdvisorResponse {
  checked_at: string
  window_hours: number
  total_requests: number
  findings: ConfigFinding[]
}

// --- Watchlist ---

export type WatchlistTargetType = 'client_ip' | 'domain' | 'user'

export interface WatchlistEntry {
  id: string
  target_type: WatchlistTargetType
  value: string
  note: string | null
  /** "" means any branch */
  branch: string
  active: boolean
  created_at: string
  last_seen_at: string | null
  last_alerted_at: string | null
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
