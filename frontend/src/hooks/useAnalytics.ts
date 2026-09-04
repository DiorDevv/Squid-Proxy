import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type {
  ActivityHeatmapResponse,
  ActorDetailResponse,
  ActorLeaderboardResponse,
  AnalyticsOverview,
  BranchBreakdownResponse,
  BranchRiskResponse,
  CategoryTrendResponse,
  DenialsResponse,
  HierarchyResponse,
  HttpBreakdownResponse,
  IngestHealthResponse,
  NewEntitiesResponse,
  ResponseTimeResponse,
  ResultCodeResponse,
  TrendGranularity,
  TrendMetric,
} from '@/types/api'

type RangeParams = Record<string, string>

export function useAnalyticsOverview(rangeParams: RangeParams, live: boolean) {
  return useQuery({
    queryKey: ['analytics-overview', rangeParams],
    queryFn: () => apiFetch<AnalyticsOverview>('/api/analytics/overview', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useCategoryTrend(
  rangeParams: RangeParams,
  granularity: TrendGranularity,
  metric: TrendMetric,
  live: boolean,
) {
  return useQuery({
    queryKey: ['analytics-category-trend', rangeParams, granularity, metric],
    queryFn: () =>
      apiFetch<CategoryTrendResponse>('/api/analytics/category-trend', {
        searchParams: { ...rangeParams, granularity, metric },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useBranchBreakdown(rangeParams: RangeParams, live: boolean) {
  return useQuery({
    queryKey: ['analytics-branch-breakdown', rangeParams],
    queryFn: () =>
      apiFetch<BranchBreakdownResponse>('/api/analytics/branch-breakdown', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useBranchRisk(rangeParams: RangeParams, live: boolean) {
  return useQuery({
    queryKey: ['analytics-branch-risk', rangeParams],
    queryFn: () =>
      apiFetch<BranchRiskResponse>('/api/analytics/branch-risk', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useActivityHeatmap(rangeParams: RangeParams, blockedOnly: boolean, live: boolean) {
  // getTimezoneOffset() is minutes *behind* UTC (positive west of UTC), so
  // negate it to get the "minutes east of UTC" the backend expects.
  const tzOffsetMinutes = -new Date().getTimezoneOffset()
  return useQuery({
    queryKey: ['analytics-activity-heatmap', rangeParams, blockedOnly, tzOffsetMinutes],
    queryFn: () =>
      apiFetch<ActivityHeatmapResponse>('/api/analytics/activity-heatmap', {
        searchParams: { ...rangeParams, blocked_only: blockedOnly, tz_offset_minutes: tzOffsetMinutes },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useResultCodes(rangeParams: RangeParams, granularity: TrendGranularity, live: boolean) {
  return useQuery({
    queryKey: ['analytics-result-codes', rangeParams, granularity],
    queryFn: () =>
      apiFetch<ResultCodeResponse>('/api/analytics/result-codes', {
        searchParams: { ...rangeParams, granularity },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useHttpBreakdown(rangeParams: RangeParams, live: boolean) {
  return useQuery({
    queryKey: ['analytics-http-breakdown', rangeParams],
    queryFn: () => apiFetch<HttpBreakdownResponse>('/api/analytics/http-breakdown', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useHierarchy(rangeParams: RangeParams, live: boolean) {
  return useQuery({
    queryKey: ['analytics-hierarchy', rangeParams],
    queryFn: () => apiFetch<HierarchyResponse>('/api/analytics/hierarchy', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useResponseTime(rangeParams: RangeParams, granularity: TrendGranularity, live: boolean) {
  return useQuery({
    queryKey: ['analytics-response-time', rangeParams, granularity],
    queryFn: () =>
      apiFetch<ResponseTimeResponse>('/api/analytics/response-time', {
        searchParams: { ...rangeParams, granularity },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useActorLeaderboard(
  rangeParams: RangeParams,
  sort: string,
  limit: number,
  live: boolean,
) {
  return useQuery({
    queryKey: ['analytics-actors', rangeParams, sort, limit],
    queryFn: () =>
      apiFetch<ActorLeaderboardResponse>('/api/analytics/actors', {
        searchParams: { ...rangeParams, sort, limit },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useActorDetail(
  rangeParams: RangeParams,
  actor: string | null,
  isUser: boolean,
) {
  return useQuery({
    queryKey: ['analytics-actor-detail', rangeParams, actor, isUser],
    queryFn: () =>
      apiFetch<ActorDetailResponse>('/api/analytics/actor-detail', {
        searchParams: { ...rangeParams, actor: actor ?? '', is_user: isUser },
      }),
    enabled: actor !== null,
  })
}

export function useNewEntities(rangeParams: RangeParams, live: boolean) {
  return useQuery({
    queryKey: ['analytics-new-entities', rangeParams],
    queryFn: () => apiFetch<NewEntitiesResponse>('/api/analytics/new-entities', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useDenials(rangeParams: RangeParams, granularity: TrendGranularity, live: boolean) {
  return useQuery({
    queryKey: ['analytics-denials', rangeParams, granularity],
    queryFn: () =>
      apiFetch<DenialsResponse>('/api/analytics/denials', { searchParams: { ...rangeParams, granularity } }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useIngestHealth(live: boolean) {
  return useQuery({
    queryKey: ['analytics-ingest-health'],
    queryFn: () => apiFetch<IngestHealthResponse>('/api/analytics/ingest-health'),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}
