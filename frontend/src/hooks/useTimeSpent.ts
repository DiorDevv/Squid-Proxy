import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { DomainCategoryLabel } from '@/types/api'

export interface DomainTimeSpent {
  domain: string
  total_seconds: number
  session_count: number
}

export interface CategoryTimeSpent {
  category: DomainCategoryLabel
  total_seconds: number
  session_count: number
}

interface TimeSpentResponse {
  items: DomainTimeSpent[]
}

interface CategoryTimeSpentResponse {
  items: CategoryTimeSpent[]
}

export function useTimeSpent(clientIp: string | undefined, rangeParams: Record<string, string>) {
  return useQuery({
    queryKey: ['time-spent', clientIp, rangeParams],
    queryFn: () =>
      apiFetch<TimeSpentResponse>(`/api/clients/${encodeURIComponent(clientIp!)}/time-spent`, {
        searchParams: rangeParams,
      }),
    enabled: Boolean(clientIp),
  })
}

export function useTimeSpentByCategory(clientIp: string | undefined, rangeParams: Record<string, string>) {
  return useQuery({
    queryKey: ['time-spent-by-category', clientIp, rangeParams],
    queryFn: () =>
      apiFetch<CategoryTimeSpentResponse>(
        `/api/clients/${encodeURIComponent(clientIp!)}/time-spent-by-category`,
        { searchParams: rangeParams },
      ),
    enabled: Boolean(clientIp),
  })
}
