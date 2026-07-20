import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { AlertSettingsOut, DomainCategoryLabel } from '@/types/api'

const ALERT_SETTINGS_QUERY_KEY = ['alert-settings']

/** Alert thresholds are per-branch (see backend app/models/alert_settings.py)
 * -- an admin edits one branch's settings at a time. */
export function useAlertSettings(branch: string) {
  return useQuery({
    queryKey: [...ALERT_SETTINGS_QUERY_KEY, branch],
    queryFn: () => apiFetch<AlertSettingsOut>('/api/alert-settings', { searchParams: { branch } }),
  })
}

interface UpdateAlertSettingsBody {
  sensitive_categories: DomainCategoryLabel[]
  non_work_minutes_threshold: number
  client_daily_byte_quota_bytes: number | null
}

export function useUpdateAlertSettings(branch: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: UpdateAlertSettingsBody) =>
      apiFetch<AlertSettingsOut>('/api/alert-settings', { method: 'PUT', body, searchParams: { branch } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [...ALERT_SETTINGS_QUERY_KEY, branch] }),
  })
}
