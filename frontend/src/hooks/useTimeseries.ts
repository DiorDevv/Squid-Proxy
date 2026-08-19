import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { Granularity, TimeseriesResponse } from '@/types/api'

export function useTimeseries(
  rangeParams: Record<string, string>,
  granularity: Granularity,
  live: boolean,
  enabled = true,
) {
  return useQuery({
    queryKey: ['timeseries', rangeParams, granularity],
    queryFn: () =>
      apiFetch<TimeseriesResponse>('/api/timeseries', { searchParams: { ...rangeParams, granularity } }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
    enabled,
  })
}
