import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { AnomalyEvent, Page } from '@/types/api'

export function useRecentInsights(limit = 10, live = false, branch: string | null = null) {
  return useQuery({
    queryKey: ['insights-recent', limit, branch],
    queryFn: () =>
      apiFetch<Page<AnomalyEvent>>('/api/insights/recent', {
        searchParams: branch ? { limit, branch } : { limit },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}
