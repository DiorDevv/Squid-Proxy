import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch, importDomainCategories } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import type {
  CategoryStatsResponse,
  DomainCategoryImportResponse,
  DomainCategoryLabel,
  DomainCategoryOut,
} from '@/types/api'

const DOMAIN_CATEGORIES_QUERY_KEY = ['domain-categories']

export function useDomainCategories() {
  return useQuery({
    queryKey: DOMAIN_CATEGORIES_QUERY_KEY,
    queryFn: () => apiFetch<DomainCategoryOut[]>('/api/domain-categories'),
  })
}

// Shared by useSetDomainCategory and useImportDomainCategories -- both
// change what's an admin-assigned override. Every place a domain's category
// is displayed -- Settings' own list, DomainDetailPage's badge/selector, the
// Domains page's rankings and by-category breakdown -- reads from a
// different query, so a change made from either mutation needs to
// invalidate all of them, not just the list it happened to be set from.
// invalidateQueries matches by key prefix, so e.g. ['top-domains'] covers
// every (rangeParams, limit, category) variant already cached.
function invalidateDomainCategoryQueries(queryClient: ReturnType<typeof useQueryClient>): void {
  queryClient.invalidateQueries({ queryKey: DOMAIN_CATEGORIES_QUERY_KEY })
  queryClient.invalidateQueries({ queryKey: ['domain-summary'] })
  queryClient.invalidateQueries({ queryKey: ['top-domains'] })
  queryClient.invalidateQueries({ queryKey: ['top-blocked'] })
  queryClient.invalidateQueries({ queryKey: ['top-data-usage'] })
  queryClient.invalidateQueries({ queryKey: ['usage-by-category'] })
}

export function useSetDomainCategory() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({ domain, category }: { domain: string; category: DomainCategoryLabel }) =>
      apiFetch<DomainCategoryOut>(`/api/domain-categories/${encodeURIComponent(domain)}`, {
        method: 'PUT',
        body: { category },
      }),
    onSuccess: () => invalidateDomainCategoryQueries(queryClient),
  })
}

export function useImportDomainCategories() {
  const queryClient = useQueryClient()
  return useMutation<DomainCategoryImportResponse, Error, File>({
    mutationFn: (file: File) => importDomainCategories(file),
    onSuccess: () => invalidateDomainCategoryQueries(queryClient),
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
