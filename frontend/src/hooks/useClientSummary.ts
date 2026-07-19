import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { ClientSummary } from '@/types/api'

export function useClientSummary(clientIp: string | undefined, rangeParams: Record<string, string>) {
  return useQuery({
    queryKey: ['client-summary', clientIp, rangeParams],
    queryFn: () =>
      apiFetch<ClientSummary>(`/api/clients/${encodeURIComponent(clientIp!)}/summary`, {
        searchParams: rangeParams,
      }),
    enabled: Boolean(clientIp),
  })
}
