import { useMemo, useRef, useState } from 'react'
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
import { useRecentInsights } from '@/hooks/useInsights'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useTranslation } from '@/i18n'
import type { Granularity } from '@/types/api'

const BUCKET_MS: Record<Granularity, number> = { minute: 60_000, hour: 3_600_000 }
const DAY_MS = 24 * BUCKET_MS.hour

/** 'minute' buckets are fine (and more useful) up to a day's worth of
 * points; past that a multi-day chart would be rendering thousands of
 * points for no visual benefit, so it switches to 'hour' instead. Backend
 * already supports both (see app/schemas/common.py's Granularity) -- this
 * is purely a frontend rendering-cost/readability choice. */
function granularityForRange(
  mode: 'preset' | 'custom',
  range: '1h' | '24h' | '7d',
  customFrom: string | null,
  customTo: string | null,
): Granularity {
  if (mode === 'custom' && customFrom && customTo) {
    const durationMs = new Date(customTo).getTime() - new Date(customFrom).getTime()
    return durationMs > DAY_MS ? 'hour' : 'minute'
  }
  return range === '7d' ? 'hour' : 'minute'
}

const SPARKLINE_POINTS = 40

/** Summary-card sparklines plot a fixed, small point count regardless of
 * how many buckets the chart itself fetched (up to ~1440 for a 24h/minute
 * view) -- a decorative strip this size has no visual use for that many
 * vertices, and evenly-strided sampling keeps it cheap no matter how wide
 * the selected range gets. */
function downsample(values: number[], targetCount: number): number[] {
  if (values.length <= targetCount) return values
  const stride = values.length / targetCount
  return Array.from({ length: targetCount }, (_, i) => values[Math.floor(i * stride)] ?? 0)
}

export default function DashboardPage() {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const rangeParams = useRangeSearchParams()
  const branch = useFiltersStore((state) => state.branch)
  const setCustomRange = useFiltersStore((state) => state.setCustomRange)
  const filterMode = useFiltersStore((state) => state.mode)
  const filterRange = useFiltersStore((state) => state.range)
  const customFrom = useFiltersStore((state) => state.customFrom)
  const customTo = useFiltersStore((state) => state.customTo)
  const { connectionState } = useLiveEvents()
  const live = connectionState === 'open'
  const trafficPanelRef = useRef<HTMLDivElement>(null)
  const [highlightedAnomalyId, setHighlightedAnomalyId] = useState<string | null>(null)

  const granularity = granularityForRange(filterMode, filterRange, customFrom, customTo)

  const summaryQuery = useSummary(rangeParams, live)
  const timeseriesQuery = useTimeseries(rangeParams, granularity, live)
  const topBlockedQuery = useTopBlocked(rangeParams, 5, live)
  // Same query InsightsPanel makes (identical queryKey) -- sharing its cache
  // rather than a second independent fetch, just to also plot markers here.
  const insightsQuery = useRecentInsights(10)

  const summary = summaryQuery.data
  const isEmptyRange = summaryQuery.isSuccess && summary?.total_requests === 0

  // Turns a chart click into a precise custom range (see filters-store's
  // setCustomRange) and hands off to /events, which already reads that same
  // range -- reusing the exact filter mechanism the range picker uses,
  // rather than a one-off query-string contract just for this entry point.
  function handleSelectBucket(bucketTs: string) {
    const start = new Date(bucketTs)
    if (Number.isNaN(start.getTime())) return
    const end = new Date(start.getTime() + BUCKET_MS[granularity])
    setCustomRange(start.toISOString(), end.toISOString())
    navigate('/events')
  }

  // Reverse direction of the chart's own anomaly markers -- clicking an
  // insight emphasizes its marker and brings the chart into view, in case
  // the panel below it (the two are stacked in separate grid rows) is
  // scrolled out of frame.
  function handleSelectInsight(id: string) {
    setHighlightedAnomalyId(id)
    trafficPanelRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' })
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

  const points = timeseriesQuery.data?.points
  const sparklines = useMemo(
    () => ({
      total: downsample(points?.map((p) => p.total_requests) ?? [], SPARKLINE_POINTS),
      blocked: downsample(points?.map((p) => p.blocked_requests) ?? [], SPARKLINE_POINTS),
      allowed: downsample(points?.map((p) => p.allowed_requests) ?? [], SPARKLINE_POINTS),
    }),
    [points],
  )

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
          sparkline={sparklines.total}
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
          sparkline={sparklines.blocked}
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
          sparkline={sparklines.allowed}
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
        <div ref={trafficPanelRef} className="xl:col-span-2">
          <Panel
            title={t('dashboard.trafficOverTime')}
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
                  anomalies={insightsQuery.data?.items ?? []}
                  live={live}
                  highlightedAnomalyId={highlightedAnomalyId}
                />
              )}
            </PanelErrorBoundary>
          </Panel>
        </div>

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
            <InsightsPanel onSelectInsight={handleSelectInsight} />
          </PanelErrorBoundary>
        </Panel>
      </div>
    </div>
  )
}
