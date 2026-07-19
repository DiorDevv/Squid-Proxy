import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type { CategoryStatsResponse, DomainCategoryLabel, DomainCategoryOut } from '@/types/api'

const DOMAIN_CATEGORIES_QUERY_KEY = ['domain-categories']

export function useDomainCategories() {
  return useQuery({
    queryKey: DOMAIN_CATEGORIES_QUERY_KEY,
    queryFn: () => apiFetch<DomainCategoryOut[]>('/api/domain-categories'),
  })
}

export function useSetDomainCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ domain, category }: { domain: string; category: DomainCategoryLabel }) =>
      apiFetch<DomainCategoryOut>(`/api/domain-categories/${encodeURIComponent(domain)}`, {
        method: 'PUT',
        body: { category },
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: DOMAIN_CATEGORIES_QUERY_KEY }),
  })
}

export function useUsageByCategory(rangeParams: Record<string, string>, live: boolean) {
  return useQuery({
    queryKey: ['usage-by-category', rangeParams],
    queryFn: () =>
      apiFetch<CategoryStatsResponse>('/api/domains/by-category', { searchParams: rangeParams }),
    refetchInterval: live ? false : POLLING_FALLBACK_INTERVAL_MS,
  })
}
