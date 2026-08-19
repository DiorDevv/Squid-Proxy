import { Link, useNavigate } from 'react-router-dom'
import { Activity, ChevronRight, Info, ShieldCheck, ShieldX, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { SummaryCard } from '@/components/dashboard/SummaryCard'
import { TrafficChart } from '@/components/dashboard/TrafficChart'
import { TopBlockedDomains } from '@/components/dashboard/TopBlockedDomains'
import { LiveEventsTicker } from '@/components/dashboard/LiveEventsTicker'
import { InsightsPanel } from '@/components/dashboard/InsightsPanel'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { RangeSelector } from '@/components/common/RangeSelector'
import { BranchSelector } from '@/components/common/BranchSelector'
import { SavedFiltersMenu } from '@/components/common/SavedFiltersMenu'
import { useFiltersStore, useRangeSearchParams } from '@/lib/filters-store'
import { getPercentChange, getPreviousPeriodParams } from '@/lib/compare-period'
import { useSummary } from '@/hooks/useSummary'
import { useTimeseries } from '@/hooks/useTimeseries'
import { useTopBlocked } from '@/hooks/useTopDomains'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useTranslation } from '@/i18n'

// This page's chart always requests 'minute' granularity (see the
// useTimeseries call below), so a clicked bucket is always exactly 60s wide.
const MINUTE_MS = 60_000

export default function DashboardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const rangeParams = useRangeSearchParams()
  const branch = useFiltersStore((state) => state.branch)
  const setCustomRange = useFiltersStore((state) => state.setCustomRange)
  const { connectionState } = useLiveEvents()
  const live = connectionState === 'open'

  const summaryQuery = useSummary(rangeParams, live)
  const timeseriesQuery = useTimeseries(rangeParams, 'minute', live)
  const topBlockedQuery = useTopBlocked(rangeParams, 5, live)

  const summary = summaryQuery.data
  const isEmptyRange = summaryQuery.isSuccess && summary?.total_requests === 0

  // Turns a chart click into a precise custom range (see filters-store's
  // setCustomRange) and hands off to /events, which already reads that same
  // range -- reusing the exact filter mechanism the range picker uses,
  // rather than a one-off query-string contract just for this entry point.
  function handleSelectBucket(bucketTs: string) {
    const start = new Date(bucketTs)
    if (Number.isNaN(start.getTime())) return
    const end = new Date(start.getTime() + MINUTE_MS)
    setCustomRange(start.toISOString(), end.toISOString())
    navigate('/events')
  }

  // Reuses the *resolved* since/until the backend already computed for the
  // current period (rather than re-deriving "what does '24h' mean" here) so
  // the previous window is always an exact, equal-duration predecessor.
  const previousPeriodParams = summary
    ? getPreviousPeriodParams(summary.since, summary.until, branch)
    : null
  const previousSummaryQuery = useSummary(
    previousPeriodParams ?? {},
    false,
    previousPeriodParams !== null,
  )
  const previousSummary = previousSummaryQuery.data

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end gap-2">
        <BranchSelector />
        <RangeSelector />
        <SavedFiltersMenu />
      </div>

      {isEmptyRange && (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
          <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t('common.noDataForRange')}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryCard
          label={t('dashboard.totalRequests')}
          value={summary?.total_requests ?? 0}
          icon={Activity}
          tone="info"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
          deltaPercent={getPercentChange(
            summary?.total_requests ?? 0,
            previousSummary?.total_requests,
          )}
        />
        <SummaryCard
          label={t('dashboard.blocked')}
          value={summary?.blocked_requests ?? 0}
          icon={ShieldX}
          tone="warning"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
          deltaPercent={getPercentChange(
            summary?.blocked_requests ?? 0,
            previousSummary?.blocked_requests,
          )}
        />
        <SummaryCard
          label={t('dashboard.allowed')}
          value={summary?.allowed_requests ?? 0}
          icon={ShieldCheck}
          tone="success"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
          deltaPercent={getPercentChange(
            summary?.allowed_requests ?? 0,
            previousSummary?.allowed_requests,
          )}
        />
        <SummaryCard
          label={t('dashboard.activeClients')}
          value={summary?.active_client_count ?? 0}
          icon={Users}
          tone="purple"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
          deltaPercent={getPercentChange(
            summary?.active_client_count ?? 0,
            previousSummary?.active_client_count,
          )}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel
          title={t('dashboard.trafficOverTime')}
          className="xl:col-span-2"
          action={
            !timeseriesQuery.isLoading &&
            (timeseriesQuery.data?.points.length ?? 0) > 0 && (
              <span className="text-xs text-muted-foreground">{t('dashboard.trafficChartHint')}</span>
            )
          }
        >
          <PanelErrorBoundary panelLabel={t('dashboard.trafficOverTime')}>
            {timeseriesQuery.isError ? (
              <ErrorState
                message={timeseriesQuery.error?.message}
                onRetry={() => timeseriesQuery.refetch()}
              />
            ) : (
              <TrafficChart
                points={timeseriesQuery.data?.points ?? []}
                loading={timeseriesQuery.isLoading}
                onSelectBucket={handleSelectBucket}
              />
            )}
          </PanelErrorBoundary>
        </Panel>

        <Panel title={t('dashboard.topBlockedDomains')}>
          <PanelErrorBoundary panelLabel={t('dashboard.topBlockedDomains')}>
            {topBlockedQuery.isError ? (
              <ErrorState
                message={topBlockedQuery.error?.message}
                onRetry={() => topBlockedQuery.refetch()}
              />
            ) : (
              <TopBlockedDomains
                items={topBlockedQuery.data?.items ?? []}
                loading={topBlockedQuery.isLoading}
              />
            )}
          </PanelErrorBoundary>
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel
          title={t('dashboard.liveEvents')}
          className="xl:col-span-2"
          action={
            <span className="flex items-center gap-1.5 text-xs text-muted-foreground">
              {t('dashboard.liveEventsHint')}
              <Button asChild variant="outline" size="xs" className="gap-0.5">
                <Link to="/blocked">
                  {t('dashboard.liveEventsHintLink')}
                  <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
                </Link>
              </Button>
            </span>
          }
        >
          <PanelErrorBoundary panelLabel={t('dashboard.liveEvents')}>
            <LiveEventsTicker />
          </PanelErrorBoundary>
        </Panel>

        <Panel title={t('dashboard.insights')}>
          <PanelErrorBoundary panelLabel={t('dashboard.insights')}>
            <InsightsPanel />
          </PanelErrorBoundary>
        </Panel>
      </div>
    </div>
  )
}
