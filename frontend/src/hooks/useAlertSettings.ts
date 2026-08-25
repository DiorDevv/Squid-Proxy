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
  uncategorized_domain_request_threshold: number | null
  telegram_chat_id: string | null
}

export function useUpdateAlertSettings(branch: string) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: UpdateAlertSettingsBody) =>
      apiFetch<AlertSettingsOut>('/api/alert-settings', { method: 'PUT', body, searchParams: { branch } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: [...ALERT_SETTINGS_QUERY_KEY, branch] }),
  })
}

/** Sends a one-off Telegram message to the given chat id without saving it
 * -- lets an admin verify a chat id before persisting it (see
 * backend/app/api/routes/alert_settings.py:test_telegram_alert). */
export function useTestTelegramAlert(branch: string) {
  return useMutation({
    mutationFn: (telegramChatId: string) =>
      apiFetch<void>('/api/alert-settings/test-telegram', {
        method: 'POST',
        body: { telegram_chat_id: telegramChatId },
        searchParams: { branch },
      }),
  })
}
