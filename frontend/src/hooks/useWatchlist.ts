import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { ApiError, apiFetch } from '@/lib/api-client'
import type { WatchlistEntry, WatchlistTargetType } from '@/types/api'

const KEY = ['watchlist']

export function useWatchlist() {
  return useQuery({
    queryKey: KEY,
    queryFn: () => apiFetch<WatchlistEntry[]>('/api/watchlist'),
  })
}

export interface CreateWatchlistBody {
  target_type: WatchlistTargetType
  value: string
  note?: string | null
  branch?: string
}

export function useCreateWatchlistEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CreateWatchlistBody) =>
      apiFetch<WatchlistEntry>('/api/watchlist', { method: 'POST', body }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useSetWatchlistActive() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, active }: { id: string; active: boolean }) =>
      apiFetch<WatchlistEntry>(`/api/watchlist/${encodeURIComponent(id)}`, {
        method: 'PATCH',
        body: { active },
      }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

export function useDeleteWatchlistEntry() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: string) =>
      apiFetch<void>(`/api/watchlist/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    onSuccess: () => qc.invalidateQueries({ queryKey: KEY }),
  })
}

/** True for the 409 the API returns when that target is already watched --
 * lets a caller show "already on the watchlist" rather than a generic error. */
export function isWatchlistConflict(error: unknown): boolean {
  return error instanceof ApiError && error.status === 409
}
