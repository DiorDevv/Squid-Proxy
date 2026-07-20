import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { BranchesResponse } from '@/types/api'

/** Configured log sources/branches (see backend Settings.effective_log_sources)
 * -- populates BranchSelector. Rarely changes (a config/redeploy concern,
 * not admin-editable business policy), so no live polling. */
export function useBranches() {
  return useQuery({
    queryKey: ['branches'],
    queryFn: () => apiFetch<BranchesResponse>('/api/branches'),
    staleTime: 5 * 60 * 1000,
  })
}
