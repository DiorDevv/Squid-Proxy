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

export function useCacheEfficiency(rangeParams: Record<string, string>, live: boolean) {
  return useQuery({
    queryKey: ['cache-efficiency', rangeParams],
    queryFn: () => apiFetch<CacheEfficiencyResponse>('/api/cache-efficiency', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}
