import { toast } from 'sonner'
import { Send } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { useReportStatus, useSendReportNow } from '@/hooks/useReports'
import { formatDateTime } from '@/lib/format'
import { ApiError } from '@/lib/api-client'
import { useTranslation } from '@/i18n'

const SCHEDULE_LABEL_KEYS = {
  disabled: 'settings.reportScheduleDisabled',
  daily: 'settings.reportScheduleDaily',
  weekly: 'settings.reportScheduleWeekly',
} as const

/** Scheduled email summary reports (see backend app/services/report_scheduler.py).
 * The schedule itself (disabled/daily/weekly) and SMTP credentials are
 * environment-configured, not editable here -- they're infrastructure
 * secrets, not a business policy an admin should tune from a web form. This
 * panel only shows status and lets an admin trigger an ad-hoc send now. */
export function ReportsPanel() {
  const { t } = useTranslation()
  const status = useReportStatus()
  const sendNow = useSendReportNow()

  function handleSendNow() {
    sendNow.mutate(undefined, {
      onSuccess: () => toast.success(t('settings.reportSentToast')),
      onError: (err) =>
        toast.error(err instanceof ApiError ? err.message : t('settings.reportSendErrorToast')),
    })
  }

  if (status.isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }

  if (status.isError) {
    return <ErrorState message={status.error?.message} onRetry={() => status.refetch()} />
  }

  const data = status.data!
  const canSend = data.recipients_configured && data.smtp_configured

  return (
    <div className="flex flex-col gap-4">
      <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted-foreground">
            {t('settings.reportSchedule')}
          </dt>
          <dd className="font-data mt-1 text-foreground">{t(SCHEDULE_LABEL_KEYS[data.schedule])}</dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted-foreground">
            {t('settings.reportLastSent')}
          </dt>
          <dd className="font-data mt-1 text-foreground">
            {data.last_sent_at ? formatDateTime(data.last_sent_at) : t('settings.reportNeverSent')}
          </dd>
        </div>
        <div>
          <dt className="text-xs uppercase tracking-wide text-muted-foreground">
            {t('settings.reportConfigured')}
          </dt>
          <dd className="font-data mt-1 text-foreground">
            {canSend ? t('settings.reportConfiguredYes') : t('settings.reportConfiguredNo')}
          </dd>
        </div>
      </dl>

      <Button
        onClick={handleSendNow}
        disabled={!canSend || sendNow.isPending}
        className="w-fit gap-2"
        variant="outline"
      >
        <Send className="h-4 w-4" aria-hidden="true" />
        {sendNow.isPending ? t('settings.reportSending') : t('settings.reportSendNow')}
      </Button>
      {!canSend && <p className="text-xs text-muted-foreground">{t('settings.reportNotConfiguredNote')}</p>}
    </div>
  )
}
