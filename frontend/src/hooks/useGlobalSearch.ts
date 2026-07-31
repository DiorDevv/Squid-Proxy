import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { ClientSummary, DomainStat, DomainStatsResponse, Page } from '@/types/api'

const RESULT_LIMIT = 5

/** Searches the widest available preset range (7d) regardless of whatever
 * range the user currently has selected on a specific page -- a global
 * search that only looked inside "the last 1h" because that happened to be
 * the active dashboard filter would silently miss most matches. */
const SEARCH_RANGE_PARAMS = { range: '7d' } as const

export function useGlobalSearch(query: string) {
  const trimmed = query.trim()
  const enabled = trimmed.length > 0

  const clientsQuery = useQuery({
    queryKey: ['global-search', 'clients', trimmed],
    queryFn: () =>
      apiFetch<Page<ClientSummary>>('/api/clients', {
        searchParams: { ...SEARCH_RANGE_PARAMS, search: trimmed, limit: RESULT_LIMIT },
      }),
    enabled,
  })

  const domainsQuery = useQuery({
    queryKey: ['global-search', 'domains', trimmed],
    queryFn: () =>
      apiFetch<DomainStatsResponse>('/api/domains/search', {
        searchParams: { ...SEARCH_RANGE_PARAMS, q: trimmed, limit: RESULT_LIMIT },
      }),
    enabled,
  })

  return {
    clients: clientsQuery.data?.items ?? [],
    domains: domainsQuery.data?.items ?? ([] as DomainStat[]),
    isLoading: enabled && (clientsQuery.isLoading || domainsQuery.isLoading),
    isError: clientsQuery.isError || domainsQuery.isError,
  }
}
