import { Activity, Info, ShieldCheck, ShieldX, Users } from 'lucide-react'
import { SummaryCard } from '@/components/dashboard/SummaryCard'
import { TrafficChart } from '@/components/dashboard/TrafficChart'
import { TopBlockedDomains } from '@/components/dashboard/TopBlockedDomains'
import { LiveEventsTicker } from '@/components/dashboard/LiveEventsTicker'
import { InsightsPanel } from '@/components/dashboard/InsightsPanel'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { RangeSelector } from '@/components/common/RangeSelector'
import { BranchSelector } from '@/components/common/BranchSelector'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useSummary } from '@/hooks/useSummary'
import { useTimeseries } from '@/hooks/useTimeseries'
import { useTopBlocked } from '@/hooks/useTopDomains'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useTranslation } from '@/i18n'

export default function DashboardPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const { connectionState } = useLiveEvents()
  const live = connectionState === 'open'

  const summaryQuery = useSummary(rangeParams, live)
  const timeseriesQuery = useTimeseries(rangeParams, 'minute', live)
  const topBlockedQuery = useTopBlocked(rangeParams, 5, live)

  const summary = summaryQuery.data
  const isEmptyRange = summaryQuery.isSuccess && summary?.total_requests === 0

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end gap-2">
        <BranchSelector />
        <RangeSelector />
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
        />
        <SummaryCard
          label={t('dashboard.blocked')}
          value={summary?.blocked_requests ?? 0}
          icon={ShieldX}
          tone="warning"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
        />
        <SummaryCard
          label={t('dashboard.allowed')}
          value={summary?.allowed_requests ?? 0}
          icon={ShieldCheck}
          tone="success"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
        />
        <SummaryCard
          label={t('dashboard.activeClients')}
          value={summary?.active_client_count ?? 0}
          icon={Users}
          tone="purple"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel title={t('dashboard.trafficOverTime')} className="xl:col-span-2">
          {timeseriesQuery.isError ? (
            <ErrorState message={timeseriesQuery.error?.message} onRetry={() => timeseriesQuery.refetch()} />
          ) : (
            <TrafficChart points={timeseriesQuery.data?.points ?? []} loading={timeseriesQuery.isLoading} />
          )}
        </Panel>

        <Panel title={t('dashboard.topBlockedDomains')}>
          {topBlockedQuery.isError ? (
            <ErrorState message={topBlockedQuery.error?.message} onRetry={() => topBlockedQuery.refetch()} />
          ) : (
            <TopBlockedDomains items={topBlockedQuery.data?.items ?? []} loading={topBlockedQuery.isLoading} />
          )}
        </Panel>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel title={t('dashboard.liveEvents')} className="xl:col-span-2">
          <LiveEventsTicker />
        </Panel>

        <Panel title={t('dashboard.insights')}>
          <InsightsPanel />
        </Panel>
      </div>
    </div>
  )
}
