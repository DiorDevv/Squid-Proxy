import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { BranchComparisonChart } from '@/components/analytics/BranchComparisonChart'
import { BranchRiskTable } from '@/components/analytics/BranchRiskTable'
import { cn } from '@/lib/utils'
import { formatBytes, formatNumber } from '@/lib/format'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useBranchBreakdown, useBranchRisk } from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'

export default function AnalyticsBranchesPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const breakdown = useBranchBreakdown(rangeParams, true)
  const risk = useBranchRisk(rangeParams, true)

  const rows = breakdown.data?.rows ?? []

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('analytics.branches.riskTitle')} action={<span className="text-xs text-muted-foreground">{t('analytics.branches.riskHint')}</span>}>
        <PanelErrorBoundary panelLabel={t('analytics.branches.riskTitle')}>
          {risk.isError ? (
            <ErrorState message={risk.error?.message} onRetry={() => risk.refetch()} />
          ) : (
            <BranchRiskTable rows={risk.data?.rows ?? []} loading={risk.isLoading} />
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('analytics.branches.comparisonTitle')}>
        <PanelErrorBoundary panelLabel={t('analytics.branches.comparisonTitle')}>
          {breakdown.isError ? (
            <ErrorState message={breakdown.error?.message} onRetry={() => breakdown.refetch()} />
          ) : (
            <BranchComparisonChart rows={rows} loading={breakdown.isLoading} />
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('analytics.branches.tableTitle')}>
        <PanelErrorBoundary panelLabel={t('analytics.branches.tableTitle')}>
          {breakdown.isLoading ? (
            <div className="h-40 animate-pulse rounded bg-muted" />
          ) : rows.length === 0 ? (
            <div className="py-6 text-center text-sm text-muted-foreground">{t('analytics.branches.empty')}</div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b border-border text-left text-xs text-muted-foreground">
                    <th className="py-2 pr-3 font-medium">{t('analytics.branches.colBranch')}</th>
                    <th className="py-2 pr-3 text-right font-medium">{t('analytics.metric.totalRequests')}</th>
                    <th className="py-2 pr-3 text-right font-medium">{t('analytics.metric.blocked')}</th>
                    <th className="py-2 pr-3 text-right font-medium">{t('analytics.branches.colBlockedRatio')}</th>
                    <th className="py-2 pr-3 text-right font-medium">{t('analytics.metric.dataTransferred')}</th>
                    <th className="py-2 pr-3 text-right font-medium">{t('analytics.metric.activeClients')}</th>
                    <th className="py-2 text-right font-medium">{t('analytics.branches.colChange')}</th>
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row) => {
                    const ratioPct = row.blocked_ratio * 100
                    const change = row.requests_pct_change
                    return (
                      <tr key={row.branch} className="border-b border-border/50">
                        <td className="py-2 pr-3 font-medium text-foreground">{row.branch}</td>
                        <td className="font-data py-2 pr-3 text-right">{formatNumber(row.total_requests)}</td>
                        <td className="font-data py-2 pr-3 text-right">{formatNumber(row.blocked_requests)}</td>
                        <td
                          className={cn(
                            'font-data py-2 pr-3 text-right',
                            ratioPct >= 40 ? 'text-destructive' : ratioPct >= 15 ? 'text-amber-500' : 'text-muted-foreground',
                          )}
                        >
                          {ratioPct.toFixed(1)}%
                        </td>
                        <td className="font-data py-2 pr-3 text-right">{formatBytes(row.total_bytes)}</td>
                        <td className="font-data py-2 pr-3 text-right">{formatNumber(row.active_client_count)}</td>
                        <td
                          className={cn(
                            'font-data py-2 text-right',
                            change === null && 'text-muted-foreground',
                            change !== null && change >= 0 && 'text-success',
                            change !== null && change < 0 && 'text-destructive',
                          )}
                        >
                          {change === null ? '—' : `${change >= 0 ? '+' : ''}${change.toFixed(0)}%`}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
