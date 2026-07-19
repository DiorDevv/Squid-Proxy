import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { DomainCategoryLabel, DomainStatsResponse } from '@/types/api'

export function useTopDomains(
  rangeParams: Record<string, string>,
  limit: number,
  live: boolean,
  category?: DomainCategoryLabel | null,
) {
  return useQuery({
    queryKey: ['top-domains', rangeParams, limit, category],
    queryFn: () =>
      apiFetch<DomainStatsResponse>('/api/top-domains', {
        searchParams: { ...rangeParams, limit, category: category ?? undefined },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useTopBlocked(
  rangeParams: Record<string, string>,
  limit: number,
  live: boolean,
  category?: DomainCategoryLabel | null,
) {
  return useQuery({
    queryKey: ['top-blocked', rangeParams, limit, category],
    queryFn: () =>
      apiFetch<DomainStatsResponse>('/api/top-blocked', {
        searchParams: { ...rangeParams, limit, category: category ?? undefined },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}

export function useTopDataUsage(
  rangeParams: Record<string, string>,
  limit: number,
  live: boolean,
  category?: DomainCategoryLabel | null,
) {
  return useQuery({
    queryKey: ['top-data-usage', rangeParams, limit, category],
    queryFn: () =>
      apiFetch<DomainStatsResponse>('/api/top-data-usage', {
        searchParams: { ...rangeParams, limit, category: category ?? undefined },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}
