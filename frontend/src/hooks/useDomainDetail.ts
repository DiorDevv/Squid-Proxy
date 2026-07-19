import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { DomainClientStat, DomainSummary, Page, SortOrder } from '@/types/api'

export function useDomainSummary(domain: string | undefined, rangeParams: Record<string, string>) {
  return useQuery({
    queryKey: ['domain-summary', domain, rangeParams],
    queryFn: () =>
      apiFetch<DomainSummary>(`/api/domains/${encodeURIComponent(domain!)}/summary`, {
        searchParams: rangeParams,
      }),
    enabled: Boolean(domain),
  })
}

interface UseDomainClientsParams {
  domain: string | undefined
  rangeParams: Record<string, string>
  limit: number
  offset: number
  sortBy: string
  order: SortOrder
}

export function useDomainClients({ domain, rangeParams, limit, offset, sortBy, order }: UseDomainClientsParams) {
  return useQuery({
    queryKey: ['domain-clients', domain, rangeParams, limit, offset, sortBy, order],
    queryFn: () =>
      apiFetch<Page<DomainClientStat>>(`/api/domains/${encodeURIComponent(domain!)}/clients`, {
        searchParams: { ...rangeParams, limit, offset, sort_by: sortBy, order },
      }),
    enabled: Boolean(domain),
    placeholderData: (previous) => previous,
  })
}
