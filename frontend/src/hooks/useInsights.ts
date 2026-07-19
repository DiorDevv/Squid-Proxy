import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { AnomalyEvent, Page } from '@/types/api'

export function useRecentInsights(limit = 10, live = false) {
  return useQuery({
    queryKey: ['insights-recent', limit],
    queryFn: () => apiFetch<Page<AnomalyEvent>>('/api/insights/recent', { searchParams: { limit } }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}
