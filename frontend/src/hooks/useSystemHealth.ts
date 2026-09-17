import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { SystemHealthResponse } from '@/types/api'

/** Settings -> System health. Cheap to compute server-side; refetched on a
 * slow interval so an open tab stays roughly current without hammering it. */
export function useSystemHealth() {
  return useQuery({
    queryKey: ['system-health'],
    queryFn: () => apiFetch<SystemHealthResponse>('/api/system-health'),
    refetchInterval: 60_000,
  })
}
