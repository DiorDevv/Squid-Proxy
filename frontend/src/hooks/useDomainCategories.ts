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
    // Every place a domain's category is displayed -- Settings' own list,
    // DomainDetailPage's badge/selector, the Domains page's rankings and
    // by-category breakdown -- reads from a different query, so an override
    // made from any one of them needs to invalidate all of them, not just
    // the list it happened to be set from. invalidateQueries matches by key
    // prefix, so e.g. ['top-domains'] covers every (rangeParams, limit,
    // category) variant already cached.
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: DOMAIN_CATEGORIES_QUERY_KEY })
      queryClient.invalidateQueries({ queryKey: ['domain-summary'] })
      queryClient.invalidateQueries({ queryKey: ['top-domains'] })
      queryClient.invalidateQueries({ queryKey: ['top-blocked'] })
      queryClient.invalidateQueries({ queryKey: ['top-data-usage'] })
      queryClient.invalidateQueries({ queryKey: ['usage-by-category'] })
    },
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
