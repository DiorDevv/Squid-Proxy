import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type {
  ActivityHeatmapResponse,
  AnalyticsOverview,
  BranchBreakdownResponse,
  BranchRiskResponse,
  CategoryTrendResponse,
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
