import { useState } from 'react'
import { toast } from 'sonner'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { useRetentionSettings, useUpdateRetentionSettings } from '@/hooks/useRetentionSettings'
import { useTranslation } from '@/i18n'
import type { RetentionSettingsOut } from '@/types/api'

/** Admin-tunable retention: the raw_events window and the
 * halt-purge-if-archiving-is-behind guard (see backend
 * app/models/retention_settings.py). The other windows stay env-only.
 * Lowering raw_events_days permanently deletes the now-out-of-window rows
 * on the next purge, so that path confirms first. */
export default function SettingsRetentionPage() {
  const query = useRetentionSettings()

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-2">
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (query.isError || !query.data) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }
  return <RetentionForm data={query.data} />
}

function RetentionForm({ data }: { data: RetentionSettingsOut }) {
  const { t } = useTranslation()
  const update = useUpdateRetentionSettings()

  const [rawDays, setRawDays] = useState(() => String(data.raw_events_days))
  const [haltEnabled, setHaltEnabled] = useState(data.halt_purge_if_archive_lag_days != null)
  const [haltDays, setHaltDays] = useState(() =>
    data.halt_purge_if_archive_lag_days != null ? String(data.halt_purge_if_archive_lag_days) : '7',
  )
  const [confirmOpen, setConfirmOpen] = useState(false)

  const parsedRaw = Math.round(Number(rawDays))
  const rawInvalid = !Number.isFinite(parsedRaw) || parsedRaw < 1 || parsedRaw > 3650
  const parsedHalt = Math.round(Number(haltDays))
  const haltInvalid = haltEnabled && (!Number.isFinite(parsedHalt) || parsedHalt < 1 || parsedHalt > 365)
  const isLowering = parsedRaw < data.raw_events_days

  function submit() {
    update.mutate(
      {
        raw_events_days: parsedRaw,
        halt_purge_if_archive_lag_days: haltEnabled ? parsedHalt : null,
      },
      {
        onSuccess: () => {
          toast.success(t('retentionSettings.saved'))
          setConfirmOpen(false)
        },
        onError: () => toast.error(t('common.errorDefault')),
      },
    )
  }

  function handleSave() {
    if (rawInvalid || haltInvalid) {
      toast.error(t('common.errorDefault'))
      return
    }
    if (isLowering) {
      setConfirmOpen(true)
      return
    }
    submit()
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('retentionSettings.rawTitle')}>
        <div className="flex max-w-md flex-col gap-1.5">
          <Label htmlFor="raw-events-days">{t('retentionSettings.rawDaysLabel')}</Label>
          <Input
            id="raw-events-days"
            type="number"
            min={1}
            max={3650}
            value={rawDays}
            onChange={(e) => setRawDays(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('retentionSettings.rawDaysDescription')}</p>
          {isLowering && !rawInvalid && (
            <p className="text-xs text-warning">
              {t('retentionSettings.loweringWarning', { from: data.raw_events_days, to: parsedRaw })}
            </p>
          )}
        </div>
      </Panel>

      <Panel title={t('retentionSettings.haltTitle')}>
        <div className="flex flex-col gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={haltEnabled}
              onChange={(e) => setHaltEnabled(e.target.checked)}
              className="h-4 w-4"
            />
            {t('retentionSettings.haltEnableLabel')}
          </label>
          {haltEnabled && (
            <div className="flex max-w-md flex-col gap-1.5">
              <Label htmlFor="halt-lag-days">{t('retentionSettings.haltDaysLabel')}</Label>
              <Input
                id="halt-lag-days"
                type="number"
                min={1}
                max={365}
                value={haltDays}
                onChange={(e) => setHaltDays(e.target.value)}
              />
            </div>
          )}
          <p className="text-xs text-muted-foreground">{t('retentionSettings.haltDescription')}</p>
        </div>
      </Panel>

      <Button onClick={handleSave} disabled={update.isPending} className="w-fit">
        {t('common.save')}
      </Button>

      <Dialog open={confirmOpen} onOpenChange={setConfirmOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('retentionSettings.confirmTitle')}</DialogTitle>
            <DialogDescription>
              {t('retentionSettings.confirmBody', { from: data.raw_events_days, to: parsedRaw })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setConfirmOpen(false)}>
              {t('common.previous')}
            </Button>
            <Button variant="destructive" onClick={submit} disabled={update.isPending}>
              {t('retentionSettings.confirmProceed')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
