import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { ClientActivityEvent, ClientSummary, Page, SortOrder } from '@/types/api'

interface UseClientsParams {
  rangeParams: Record<string, string>
  limit: number
  offset: number
  sortBy: string
  order: SortOrder
  live: boolean
  search?: string
}

export function useClients({ rangeParams, limit, offset, sortBy, order, live, search }: UseClientsParams) {
  return useQuery({
    queryKey: ['clients', rangeParams, limit, offset, sortBy, order, search],
    queryFn: () =>
      apiFetch<Page<ClientSummary>>('/api/clients', {
        searchParams: { ...rangeParams, limit, offset, sort_by: sortBy, order, search: search || undefined },
      }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
    placeholderData: (previous) => previous,
  })
}

interface UseClientActivityParams {
  clientIp: string | undefined
  rangeParams: Record<string, string>
  limit: number
  offset: number
  blockedOnly: boolean
  domain?: string
  method?: string
}

export function useClientActivity({
  clientIp,
  rangeParams,
  limit,
  offset,
  blockedOnly,
  domain,
  method,
}: UseClientActivityParams) {
  return useQuery({
    queryKey: ['client-activity', clientIp, rangeParams, limit, offset, blockedOnly, domain, method],
    queryFn: () =>
      apiFetch<Page<ClientActivityEvent>>(`/api/clients/${encodeURIComponent(clientIp!)}/activity`, {
        searchParams: {
          ...rangeParams,
          limit,
          offset,
          blocked_only: blockedOnly,
          domain: domain || undefined,
          method: method || undefined,
        },
      }),
    enabled: Boolean(clientIp),
    placeholderData: (previous) => previous,
  })
}
