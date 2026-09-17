import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { useDataPolicy } from '@/hooks/usePolicy'
import { useTranslation } from '@/i18n'

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd className="font-data mt-1 text-foreground">{value}</dd>
    </div>
  )
}

/** Read-only statement of what this deployment collects, why, and for how
 * long -- assembled from settings already in effect (see GET /api/policy),
 * not hand-written prose that can drift from reality. Visible to admin and
 * auditor (see docs/PRODUCT.md #3: retention & lawful-basis surface). */
export default function SettingsPolicyPage() {
  const { t } = useTranslation()
  const query = useDataPolicy()

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-32 w-full" />
        <Skeleton className="h-48 w-full" />
      </div>
    )
  }

  if (query.isError || !query.data) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }

  const policy = query.data
  const days = (n: number) => t('policy.days', { count: n })

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('policy.purposeTitle')}>
        <PanelErrorBoundary panelLabel={t('policy.purposeTitle')}>
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
            <Stat label={t('policy.purpose')} value={policy.purpose ?? t('policy.notConfigured')} />
            <Stat label={t('policy.controller')} value={policy.controller ?? t('policy.notConfigured')} />
          </dl>
          {!policy.purpose && !policy.controller && (
            <p className="mt-3 text-xs text-muted-foreground">{t('policy.notConfiguredHint')}</p>
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('policy.retentionTitle')}>
        <PanelErrorBoundary panelLabel={t('policy.retentionTitle')}>
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2 lg:grid-cols-3">
            <Stat label={t('policy.retentionRawEvents')} value={days(policy.retention.raw_events_days)} />
            <Stat label={t('policy.retentionAggregates')} value={days(policy.retention.aggregates_days)} />
            <Stat
              label={t('policy.retentionOpsAggregates')}
              value={days(policy.retention.ops_aggregates_days)}
            />
            <Stat label={t('policy.retentionArchives')} value={days(policy.retention.archives_days)} />
            <Stat
              label={t('policy.retentionClientRollup')}
              value={t('policy.hours', { count: policy.retention.client_minute_rollup_after_hours })}
            />
          </dl>
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('policy.archivingTitle')}>
        <PanelErrorBoundary panelLabel={t('policy.archivingTitle')}>
          <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-3">
            <Stat
              label={t('policy.archivingEnabled')}
              value={policy.archiving.enabled ? t('common.yes') : t('common.no')}
            />
            <Stat
              label={t('policy.archivingEncrypted')}
              value={policy.archiving.encrypted ? t('common.yes') : t('common.no')}
            />
            <Stat label={t('policy.archivingLocation')} value={policy.archiving.output_dir} />
          </dl>
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('policy.collectedFieldsTitle')}>
        <PanelErrorBoundary panelLabel={t('policy.collectedFieldsTitle')}>
          <ul className="flex flex-col divide-y divide-border">
            {policy.collected_fields.map((field) => (
              <li key={field.name} className="flex flex-col gap-0.5 py-2 text-sm sm:flex-row sm:gap-3">
                <span className="font-data w-40 shrink-0 font-medium text-foreground">{field.name}</span>
                <span className="text-muted-foreground">{field.description}</span>
              </li>
            ))}
          </ul>
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
