import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { filterParams, type BlockFilterValues } from '@/lib/block-filters'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { BlockKind, Page } from '@/types/api'
import type { LiveEvent } from '@/types/events'

interface UseEventsParams {
  rangeParams: Record<string, string>
  limit: number
  offset: number
  blockedOnly?: boolean
  /** with blockedOnly: 'denied' drops 407 login challenges, 'auth' keeps only them */
  blockKind?: BlockKind
  /** the Blocked page's shared domain/client/login/proxy filters */
  filters?: BlockFilterValues
  clientIp?: string
  domain?: string
  method?: string
  search?: string
  live?: boolean
  enabled?: boolean
}

/** DB-backed, paginated, filterable event log -- unlike useRecentEvents
 * (in-memory ring buffer, live-tail only), this reads from raw_events so it
 * can page arbitrarily far back within the retention window and filter
 * server-side, the same way useClients/useClientActivity do. */
export function useEvents({
  rangeParams,
  limit,
  offset,
  blockedOnly,
  blockKind,
  filters,
  clientIp,
  domain,
  method,
  search,
  live,
  enabled = true,
}: UseEventsParams) {
  return useQuery({
    queryKey: [
      'events', rangeParams, limit, offset, blockedOnly, blockKind, filters, clientIp, domain, method, search,
    ],
    queryFn: () =>
      apiFetch<Page<LiveEvent>>('/api/events', {
        searchParams: {
          ...rangeParams,
          ...(filters ? filterParams(filters) : {}),
          limit,
          offset,
          blocked_only: blockedOnly,
          block_kind: blockedOnly ? blockKind : undefined,
          client_ip: clientIp || undefined,
          domain: domain || undefined,
          method: method || undefined,
          search: search || undefined,
        },
      }),
    enabled,
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
    placeholderData: (previous) => previous,
  })
}
