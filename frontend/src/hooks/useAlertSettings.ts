import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { AlertSettingsOut, DomainCategoryLabel } from '@/types/api'

const ALERT_SETTINGS_QUERY_KEY = ['alert-settings']

export function useAlertSettings() {
  return useQuery({
    queryKey: ALERT_SETTINGS_QUERY_KEY,
    queryFn: () => apiFetch<AlertSettingsOut>('/api/alert-settings'),
  })
}

interface UpdateAlertSettingsBody {
  sensitive_categories: DomainCategoryLabel[]
  non_work_minutes_threshold: number
  client_daily_byte_quota_bytes: number | null
}

export function useUpdateAlertSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: UpdateAlertSettingsBody) =>
      apiFetch<AlertSettingsOut>('/api/alert-settings', { method: 'PUT', body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ALERT_SETTINGS_QUERY_KEY }),
  })
}
