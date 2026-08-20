import { Panel } from '@/components/common/Panel'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import { useTranslation } from '@/i18n'

export default function SettingsGeneralPage() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('settings.liveUpdates')}>
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              {t('settings.realtimeTransport')}
            </dt>
            <dd className="font-data mt-1 text-foreground">{t('settings.realtimeTransportValue')}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              {t('settings.pollingInterval')}
            </dt>
            <dd className="font-data mt-1 text-foreground">{POLLING_FALLBACK_INTERVAL_MS / 1000}s</dd>
          </div>
        </dl>
        <p className="text-xs text-muted-foreground">{t('settings.liveUpdatesDescription')}</p>
      </Panel>
    </div>
  )
}
