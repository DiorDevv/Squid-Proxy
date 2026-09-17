import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { cn } from '@/lib/utils'
import { formatBytes, formatNumber, formatRelativeTime, isStale } from '@/lib/format'
import { useSystemHealth } from '@/hooks/useSystemHealth'
import { useTranslation } from '@/i18n'

function Stat({ label, value, tone }: { label: string; value: string; tone?: 'warn' | 'bad' }) {
  return (
    <div>
      <dt className="text-xs uppercase tracking-wide text-muted-foreground">{label}</dt>
      <dd
        className={cn(
          'font-data mt-1',
          tone === 'bad' ? 'text-destructive' : tone === 'warn' ? 'text-warning' : 'text-foreground',
        )}
      >
        {value}
      </dd>
    </div>
  )
}

/** Settings -> System health: backup / off-site status, database size and
 * growth, disk, per-branch ingestion, background-job health, and the
 * operational-failure log. Admin/auditor (GET /api/system-health). */
export default function SettingsSystemHealthPage() {
  const { t } = useTranslation()
  const query = useSystemHealth()

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-4">
        <Skeleton className="h-28 w-full" />
        <Skeleton className="h-40 w-full" />
        <Skeleton className="h-40 w-full" />
      </div>
    )
  }
  if (query.isError || !query.data) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }

  const d = query.data
  const yn = (b: boolean | null | undefined) => (b == null ? '—' : b ? t('common.yes') : t('common.no'))

  return (
    <div className="flex flex-col gap-4">
      {/* Backup */}
      <Panel title={t('sysHealth.backupTitle')}>
        <PanelErrorBoundary panelLabel={t('sysHealth.backupTitle')}>
          {d.backup == null ? (
            <p className="text-sm text-muted-foreground">{t('sysHealth.backupNoData')}</p>
          ) : (
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Stat
                label={t('sysHealth.lastSuccess')}
                value={formatRelativeTime(d.backup.last_success_at)}
                tone={d.backup.stale ? 'bad' : undefined}
              />
              <Stat
                label={t('sysHealth.lastResult')}
                value={d.backup.ok == null ? '—' : d.backup.ok ? t('sysHealth.ok') : t('sysHealth.failed')}
                tone={d.backup.ok === false ? 'bad' : undefined}
              />
              <Stat
                label={t('sysHealth.lastSize')}
                value={d.backup.last_dump_bytes != null ? formatBytes(d.backup.last_dump_bytes) : '—'}
              />
              <Stat
                label={t('sysHealth.consecutiveFailures')}
                value={String(d.backup.consecutive_failures ?? 0)}
                tone={(d.backup.consecutive_failures ?? 0) > 0 ? 'warn' : undefined}
              />
              {d.backup.disk_free_bytes != null && d.backup.disk_total_bytes != null && (
                <Stat
                  label={t('sysHealth.backupVolumeFree')}
                  value={`${formatBytes(d.backup.disk_free_bytes)} / ${formatBytes(d.backup.disk_total_bytes)}`}
                />
              )}
              {d.backup.error && (
                <div className="col-span-2 sm:col-span-4">
                  <Stat label={t('sysHealth.error')} value={d.backup.error} tone="bad" />
                </div>
              )}
            </dl>
          )}
        </PanelErrorBoundary>
      </Panel>

      {/* Off-site */}
      <Panel title={t('sysHealth.offsiteTitle')}>
        <PanelErrorBoundary panelLabel={t('sysHealth.offsiteTitle')}>
          {d.offsite == null ? (
            <p className="text-sm text-muted-foreground">{t('sysHealth.offsiteNoData')}</p>
          ) : d.offsite.enabled === false ? (
            <p className="text-sm text-muted-foreground">{t('sysHealth.offsiteDisabled')}</p>
          ) : (
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
              <Stat label={t('sysHealth.repo')} value={d.offsite.repo ?? '—'} />
              <Stat
                label={t('sysHealth.lastSync')}
                value={formatRelativeTime(d.offsite.last_sync_at)}
                tone={d.offsite.last_sync_ok === false ? 'bad' : undefined}
              />
              <Stat
                label={t('sysHealth.lastCheck')}
                value={formatRelativeTime(d.offsite.last_check_at)}
                tone={d.offsite.last_check_ok === false ? 'bad' : undefined}
              />
              <Stat label={t('sysHealth.syncOk')} value={yn(d.offsite.last_sync_ok)} />
              {d.offsite.error && (
                <div className="col-span-2 sm:col-span-4">
                  <Stat label={t('sysHealth.error')} value={d.offsite.error} tone="bad" />
                </div>
              )}
            </dl>
          )}
        </PanelErrorBoundary>
      </Panel>

      {/* Database + disk */}
      <Panel title={t('sysHealth.databaseTitle')}>
        <PanelErrorBoundary panelLabel={t('sysHealth.databaseTitle')}>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <Stat
              label={t('sysHealth.dbSize')}
              value={d.database.total_bytes != null ? formatBytes(d.database.total_bytes) : '—'}
            />
            <Stat label={t('sysHealth.rawRows')} value={formatNumber(d.database.raw_events_row_count)} />
            <Stat label={t('sysHealth.rawAdded24h')} value={formatNumber(d.database.raw_events_added_24h)} />
            <Stat
              label={t('sysHealth.rawWindow')}
              value={
                d.database.raw_events_oldest
                  ? `${formatRelativeTime(d.database.raw_events_oldest)} → ${formatRelativeTime(d.database.raw_events_newest)}`
                  : '—'
              }
            />
            {d.disk && (
              <>
                <Stat
                  label={t('sysHealth.diskFree')}
                  value={`${formatBytes(d.disk.free_bytes)} / ${formatBytes(d.disk.total_bytes)}`}
                  tone={d.disk.used_pct >= 90 ? 'bad' : d.disk.used_pct >= 80 ? 'warn' : undefined}
                />
                <Stat label={t('sysHealth.diskUsed')} value={`${d.disk.used_pct.toFixed(0)}%`} />
              </>
            )}
          </dl>
          {d.database.tables.length > 0 && (
            <ul className="mt-4 flex flex-col divide-y divide-border text-sm">
              {d.database.tables.map((tbl) => (
                <li key={tbl.name} className="flex items-center justify-between py-1.5">
                  <span className="font-data truncate text-foreground">{tbl.name}</span>
                  <span className="font-data text-xs text-muted-foreground">{formatBytes(tbl.bytes)}</span>
                </li>
              ))}
            </ul>
          )}
        </PanelErrorBoundary>
      </Panel>

      {/* Ingestion */}
      <Panel title={t('sysHealth.ingestionTitle')}>
        <PanelErrorBoundary panelLabel={t('sysHealth.ingestionTitle')}>
          {d.ingestion.aggregator_events_likely_lost && (
            <p className="mb-3 text-sm text-destructive">{t('sysHealth.eventsDropping')}</p>
          )}
          <ul className="flex flex-col divide-y divide-border text-sm">
            {d.ingestion.branches.map((b) => {
              const stale = isStale(b.last_event_at, 60 * 60 * 1000)
              return (
                <li key={b.branch} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:gap-4">
                  <span
                    className={cn(
                      'w-28 shrink-0 font-medium',
                      !b.tailer_alive || stale ? 'text-destructive' : 'text-foreground',
                    )}
                  >
                    {b.branch}
                  </span>
                  <span className="font-data text-xs text-muted-foreground">
                    {t('sysHealth.lastEvent')}: {formatRelativeTime(b.last_event_at)}
                  </span>
                  <span className="font-data text-xs text-muted-foreground">
                    {t('sysHealth.parseFailRate')}:{' '}
                    {b.parse_failure_rate == null ? '—' : `${(b.parse_failure_rate * 100).toFixed(1)}%`}
                  </span>
                  <span
                    className={cn(
                      'font-data text-xs',
                      b.tailer_alive ? 'text-muted-foreground' : 'text-destructive',
                    )}
                  >
                    {b.tailer_alive ? t('sysHealth.tailerAlive') : t('sysHealth.tailerDown')}
                  </span>
                </li>
              )
            })}
          </ul>
          {d.ingestion.unarchived_purge_branches.length > 0 && (
            <p className="mt-3 text-xs text-warning">
              {t('sysHealth.unarchivedPurge', {
                branches: d.ingestion.unarchived_purge_branches.join(', '),
              })}
            </p>
          )}
        </PanelErrorBoundary>
      </Panel>

      {/* Background jobs */}
      <Panel title={t('sysHealth.jobsTitle')}>
        <PanelErrorBoundary panelLabel={t('sysHealth.jobsTitle')}>
          <ul className="flex flex-col divide-y divide-border text-sm">
            {d.background_jobs.map((j) => (
              <li key={j.name} className="flex flex-col gap-1 py-2 sm:flex-row sm:items-center sm:gap-4">
                <span
                  className={cn(
                    'w-56 shrink-0 font-medium',
                    !j.alive || j.last_error ? 'text-destructive' : 'text-foreground',
                  )}
                >
                  {j.name}
                </span>
                <span className="font-data text-xs text-muted-foreground">
                  {j.alive ? t('sysHealth.jobAlive') : t('sysHealth.jobStopped')}
                </span>
                <span className="font-data text-xs text-muted-foreground">
                  {t('sysHealth.lastRun')}: {formatRelativeTime(j.last_run_at)}
                </span>
                {j.last_error && (
                  <span className="font-data min-w-0 flex-1 truncate text-xs text-destructive" title={j.last_error}>
                    {j.consecutive_failures}× · {j.last_error}
                  </span>
                )}
              </li>
            ))}
          </ul>
        </PanelErrorBoundary>
      </Panel>

      {/* Recent failures */}
      <Panel title={t('sysHealth.eventsTitle')}>
        <PanelErrorBoundary panelLabel={t('sysHealth.eventsTitle')}>
          {d.recent_events.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('sysHealth.eventsEmpty')}</p>
          ) : (
            <ul className="flex max-h-96 flex-col gap-2 overflow-y-auto text-sm">
              {d.recent_events.map((e, i) => (
                <li key={i} className="flex flex-col gap-0.5 rounded-md border border-border bg-secondary/40 px-3 py-2">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-data text-xs font-medium text-foreground">{e.source}</span>
                    <span className="font-data text-[10px] text-muted-foreground">
                      {formatRelativeTime(e.created_at)}
                    </span>
                  </div>
                  <p className="text-xs text-muted-foreground">{e.message}</p>
                </li>
              ))}
            </ul>
          )}
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
