import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { LiveEvent } from '@/types/events'

interface UseRecentEventsParams {
  limit: number
  blockedOnly?: boolean
  clientIp?: string
}

export function useRecentEvents({ limit, blockedOnly, clientIp }: UseRecentEventsParams) {
  return useQuery({
    queryKey: ['events-recent', limit, blockedOnly, clientIp],
    queryFn: () =>
      apiFetch<LiveEvent[]>('/api/events/recent', {
        searchParams: { limit, blocked_only: blockedOnly, client_ip: clientIp },
      }),
    refetchInterval: POLLING_FALLBACK_INTERVAL_MS,
  })
}
