import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { ExportCleanupMode, ExportSettingsOut } from '@/types/api'

const EXPORT_SETTINGS_QUERY_KEY = ['export-settings']

/** Export cleanup policy is global, not per-branch (see backend
 * app/models/export_settings.py) -- unlike useAlertSettings, there's no
 * branch argument here. */
export function useExportSettings() {
  return useQuery({
    queryKey: EXPORT_SETTINGS_QUERY_KEY,
    queryFn: () => apiFetch<ExportSettingsOut>('/api/export-settings'),
  })
}

interface UpdateExportSettingsBody {
  cleanup_mode: ExportCleanupMode
  retention_hours: number
  warn_undownloaded_after_hours: number | null
}

export function useUpdateExportSettings() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (body: UpdateExportSettingsBody) =>
      apiFetch<ExportSettingsOut>('/api/export-settings', { method: 'PUT', body }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: EXPORT_SETTINGS_QUERY_KEY }),
  })
}
