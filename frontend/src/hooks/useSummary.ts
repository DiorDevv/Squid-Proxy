import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { CacheEfficiencyResponse, SummaryResponse } from '@/types/api'

export function useSummary(rangeParams: Record<string, string>, live: boolean, enabled = true) {
  return useQuery({
    queryKey: ['summary', rangeParams],
    queryFn: () => apiFetch<SummaryResponse>('/api/summary', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
    enabled,
  })
}

/** The dashboard's compare-to-previous-period summary. A closed past window
 * doesn't change, so it lives under its own key (outside useWebSocket's
 * live-invalidated ['summary'] prefix) and is never polled -- it refetches
 * only when getPreviousPeriodParams' minute-snapped window moves on. */
export function usePreviousSummary(params: Record<string, string> | null) {
  return useQuery({
    queryKey: ['summary-previous', params],
    queryFn: () => apiFetch<SummaryResponse>('/api/summary', { searchParams: params ?? {} }),
    enabled: params !== null,
    staleTime: Infinity,
  })
}

export function useCacheEfficiency(rangeParams: Record<string, string>, live: boolean) {
  return useQuery({
    queryKey: ['cache-efficiency', rangeParams],
    queryFn: () => apiFetch<CacheEfficiencyResponse>('/api/cache-efficiency', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}
