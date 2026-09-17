import { cn } from '@/lib/utils'
import { formatNumber } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { IngestHealthResponse } from '@/types/api'

interface IngestHealthPanelProps {
  data?: IngestHealthResponse
  loading?: boolean
}

/** Per-branch log-ingestion health: is the tailer alive, is Squid logging
 * in a format we can parse, is the aggregator keeping up. Without this the
 * risk score above it could look calm simply because no logs are arriving. */
export function IngestHealthPanel({ data, loading }: IngestHealthPanelProps) {
  const { t } = useTranslation()

  if (loading) {
    return <div className="h-32 w-full animate-pulse rounded-md bg-muted" />
  }
  if (!data || data.branches.length === 0) {
    return (
      <div className="py-6 text-center text-sm text-muted-foreground">{t('analytics.branches.empty')}</div>
    )
  }

  const backlogPct = Math.round(data.aggregator_backlog_ratio * 100)

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-4 text-sm">
        <span className="text-muted-foreground">
          {t('analytics.ingest.backlog')}:{' '}
          <span
            className={cn(
              'font-data font-medium',
              backlogPct >= 80 ? 'text-destructive' : backlogPct >= 40 ? 'text-amber-500' : 'text-success',
            )}
          >
            {backlogPct}%
          </span>
        </span>
        {data.aggregator_events_likely_lost && (
          <span className="font-data rounded bg-destructive/10 px-1.5 py-0.5 text-xs font-semibold text-destructive">
            {t('analytics.ingest.eventsLost')}
          </span>
        )}
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[480px] text-sm">
          <thead>
            <tr className="border-b border-border text-left text-xs text-muted-foreground">
              <th className="py-2 pr-3 font-medium">{t('analytics.branches.colBranch')}</th>
              <th className="py-2 pr-3 font-medium">{t('analytics.ingest.tailer')}</th>
              <th className="py-2 pr-3 text-right font-medium">{t('analytics.ingest.parseFailure')}</th>
              <th className="py-2 text-right font-medium">{t('analytics.ingest.linesParsed')}</th>
            </tr>
          </thead>
          <tbody>
            {data.branches.map((b) => {
              const failPct = b.parse_failure_rate === null ? null : b.parse_failure_rate * 100
              return (
                <tr key={b.branch} className="border-b border-border/50">
                  <td className="py-2 pr-3 font-medium text-foreground">{b.branch}</td>
                  <td className="py-2 pr-3">
                    <span
                      className={cn(
                        'inline-flex items-center gap-1.5',
                        b.tailer_alive ? 'text-success' : 'text-destructive',
                      )}
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
                      {b.tailer_alive ? t('analytics.ingest.alive') : t('analytics.ingest.down')}
                    </span>
                  </td>
                  <td
                    className={cn(
                      'font-data py-2 pr-3 text-right',
                      failPct === null
                        ? 'text-muted-foreground'
                        : failPct >= 50
                          ? 'text-destructive'
                          : failPct > 0
                            ? 'text-amber-500'
                            : 'text-success',
                    )}
                  >
                    {failPct === null ? '—' : `${failPct.toFixed(1)}%`}
                  </td>
                  <td className="font-data py-2 text-right text-muted-foreground">
                    {formatNumber(b.lines_parsed)} / {formatNumber(b.lines_seen)}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
