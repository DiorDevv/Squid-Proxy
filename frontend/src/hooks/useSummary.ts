import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { SummaryResponse } from '@/types/api'

export function useSummary(rangeParams: Record<string, string>, live: boolean, enabled = true) {
  return useQuery({
    queryKey: ['summary', rangeParams],
    queryFn: () => apiFetch<SummaryResponse>('/api/summary', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
    enabled,
  })
}
