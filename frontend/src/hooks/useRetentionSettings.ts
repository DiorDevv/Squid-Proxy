import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { RetentionSettingsOut, UpdateRetentionSettingsBody } from '@/types/api'

const RETENTION_SETTINGS_QUERY_KEY = ['retention-settings']

export function useRetentionSettings() {
  return useQuery({
    queryKey: RETENTION_SETTINGS_QUERY_KEY,
    queryFn: () => apiFetch<RetentionSettingsOut>('/api/retention-settings'),
  })
}

export function useUpdateRetentionSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: UpdateRetentionSettingsBody) =>
      apiFetch<RetentionSettingsOut>('/api/retention-settings', { method: 'PUT', body }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: RETENTION_SETTINGS_QUERY_KEY })
      // The Data policy page and analytics retention tile read the same window.
      queryClient.invalidateQueries({ queryKey: ['data-policy'] })
      queryClient.invalidateQueries({ queryKey: ['analytics-retention'] })
    },
  })
}
