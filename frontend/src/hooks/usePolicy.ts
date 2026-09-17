import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { DataPolicy } from '@/types/api'

/** Settings -> Data policy: what this deployment records, why, and for how
 * long. Static per-deployment config, not live traffic data, so a long
 * staleTime is fine. */
export function useDataPolicy() {
  return useQuery({
    queryKey: ['data-policy'],
    queryFn: () => apiFetch<DataPolicy>('/api/policy'),
    staleTime: 60 * 60 * 1000,
  })
}
