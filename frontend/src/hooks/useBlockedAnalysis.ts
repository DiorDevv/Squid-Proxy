import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import { filterParams, type BlockFilterValues } from '@/lib/block-filters'
import type { BlockGroupBy, BlockGroupSort, BlockGroupsResponse, BlockKind, BlockSummary } from '@/types/api'

interface Common {
  rangeParams: Record<string, string>
  filters: BlockFilterValues
  kind: BlockKind
  enabled?: boolean
}

/** Headline numbers + hourly series for the filtered blocks -- served from
 * the hourly aggregates, so a week is as quick as a day. */
export function useBlockSummary({ rangeParams, filters, kind, enabled = true }: Common) {
  return useQuery({
    queryKey: ['blocked-summary', rangeParams, filters, kind],
    queryFn: () =>
      apiFetch<BlockSummary>('/api/blocked/summary', {
        searchParams: { ...rangeParams, ...filterParams(filters), kind },
      }),
    enabled,
    placeholderData: (previous) => previous,
  })
}

export function useBlockGroups({
  rangeParams,
  filters,
  kind,
  group,
  sort,
  limit,
  offset,
  enabled = true,
}: Common & { group: BlockGroupBy; sort: BlockGroupSort; limit: number; offset: number }) {
  return useQuery({
    queryKey: ['blocked-groups', rangeParams, filters, kind, group, sort, limit, offset],
    queryFn: () =>
      apiFetch<BlockGroupsResponse>('/api/blocked/groups', {
        searchParams: { ...rangeParams, ...filterParams(filters), kind, group, sort, limit, offset },
      }),
    enabled,
    placeholderData: (previous) => previous,
  })
}
