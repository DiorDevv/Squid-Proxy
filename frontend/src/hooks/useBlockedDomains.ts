import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { BlockedDomainSort, BlockedDomainsResponse, BlockKind } from '@/types/api'

interface UseBlockedDomainsParams {
  rangeParams: Record<string, string>
  limit: number
  offset: number
  kind: BlockKind
  sort: BlockedDomainSort
  proxy?: string
  search?: string
  enabled?: boolean
}

/** Blocked requests grouped by domain -- served from hourly aggregates, so
 * it pages a week of traffic as quickly as a day. */
export function useBlockedDomains({
  rangeParams,
  limit,
  offset,
  kind,
  sort,
  proxy,
  search,
  enabled = true,
}: UseBlockedDomainsParams) {
  return useQuery({
    queryKey: ['blocked-domains', rangeParams, limit, offset, kind, sort, proxy, search],
    queryFn: () =>
      apiFetch<BlockedDomainsResponse>('/api/blocked-domains', {
        searchParams: {
          ...rangeParams,
          limit,
          offset,
          kind,
          sort,
          proxy: proxy || undefined,
          search: search || undefined,
        },
      }),
    enabled,
    placeholderData: (previous) => previous,
  })
}
