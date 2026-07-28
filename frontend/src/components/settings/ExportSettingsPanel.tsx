import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorState } from '@/components/common/ErrorState'
import { useExportSettings, useUpdateExportSettings } from '@/hooks/useExportSettings'
import { useTranslation } from '@/i18n'
import type { ExportCleanupMode, ExportSettingsOut } from '@/types/api'

/** Admin-tunable export cleanup policy (see backend
 * app/models/export_settings.py): whether finished export files are kept
 * for a fixed number of hours (TIME_BASED) or deleted the moment they're
 * downloaded (AFTER_DOWNLOAD) -- the two are mutually exclusive, not
 * combined. Independently, warn_undownloaded_after_hours raises a
 * dashboard anomaly once a finished export has sat undownloaded that
 * long, in either mode -- off by default. */
export function ExportSettingsPanel() {
  const query = useExportSettings()

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }

  if (query.isError) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }

  if (!query.data) {
    return null
  }

  return <ExportSettingsForm data={query.data} />
}

function ExportSettingsForm({ data }: { data: ExportSettingsOut }) {
  const { t } = useTranslation()
  const updateSettings = useUpdateExportSettings()

  const [cleanupMode, setCleanupMode] = useState<ExportCleanupMode>(data.cleanup_mode)
  const [retentionHours, setRetentionHours] = useState(() => String(data.retention_hours))
  const [warnAfterHours, setWarnAfterHours] = useState(() =>
    data.warn_undownloaded_after_hours != null ? String(data.warn_undownloaded_after_hours) : '',
  )

  function handleSave() {
    const retention = Number(retentionHours)
    const retentionIsInvalid = !Number.isFinite(retention) || retention <= 0
    const trimmedWarn = warnAfterHours.trim()
    const warnValue = trimmedWarn ? Math.round(Number(trimmedWarn)) : null
    const warnIsInvalid = trimmedWarn !== '' && (!Number.isFinite(Number(trimmedWarn)) || warnValue! <= 0)
    if (retentionIsInvalid || warnIsInvalid) {
      toast.error(t('common.errorDefault'))
      return
    }

    updateSettings.mutate(
      {
        cleanup_mode: cleanupMode,
        retention_hours: Math.round(retention),
        warn_undownloaded_after_hours: warnValue,
      },
      {
        onSuccess: () => toast.success(t('settings.exportSettingsSaved')),
        onError: () => toast.error(t('common.errorDefault')),
      },
    )
  }

  return (
    <>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="export-cleanup-mode">{t('settings.exportCleanupMode')}</Label>
          <Select value={cleanupMode} onValueChange={(v) => setCleanupMode(v as ExportCleanupMode)}>
            <SelectTrigger id="export-cleanup-mode">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="time_based">{t('settings.exportCleanupModeTimeBased')}</SelectItem>
              <SelectItem value="after_download">{t('settings.exportCleanupModeAfterDownload')}</SelectItem>
            </SelectContent>
          </Select>
          <p className="text-xs text-muted-foreground">{t('settings.exportCleanupModeDescription')}</p>
        </div>

        {cleanupMode === 'time_based' && (
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="export-retention-hours">{t('settings.exportRetentionHours')}</Label>
            <Input
              id="export-retention-hours"
              type="number"
              min={1}
              value={retentionHours}
              onChange={(e) => setRetentionHours(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">{t('settings.exportRetentionHoursDescription')}</p>
          </div>
        )}

        <div className="flex flex-col gap-1.5">
          <Label htmlFor="export-warn-hours">{t('settings.exportWarnUndownloadedHours')}</Label>
          <Input
            id="export-warn-hours"
            type="number"
            min={1}
            placeholder={t('settings.exportWarnUndownloadedHoursPlaceholder')}
            value={warnAfterHours}
            onChange={(e) => setWarnAfterHours(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('settings.exportWarnUndownloadedHoursDescription')}</p>
        </div>
      </div>

      <Button onClick={handleSave} disabled={updateSettings.isPending} className="w-fit">
        {t('common.save')}
      </Button>
    </>
  )
}
