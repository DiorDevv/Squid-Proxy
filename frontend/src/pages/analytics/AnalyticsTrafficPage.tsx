import { useState } from 'react'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { BreakdownBars } from '@/components/analytics/BreakdownBars'
import { StackedAreaOverTime } from '@/components/analytics/StackedAreaOverTime'
import { ResponseTimeChart } from '@/components/analytics/ResponseTimeChart'
import { CategoryTrendChart } from '@/components/analytics/CategoryTrendChart'
import { CategoryBreakdownList } from '@/components/analytics/CategoryBreakdownList'
import { ActivityHeatmap } from '@/components/analytics/ActivityHeatmap'
import { MiniStat } from '@/components/analytics/MiniStat'
import { Toggle } from '@/components/analytics/Toggle'
import { OpsRetentionNote } from '@/components/analytics/OpsRetentionNote'
import { formatLatencyMs as ms } from '@/lib/format'
import { durationBandColor, resultCodeColor } from '@/lib/ops-colors'
import { useRangeSearchParams } from '@/lib/filters-store'
import {
  useActivityHeatmap,
  useCategoryTrend,
  useResponseTime,
  useResultCodes,
} from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'
import type { TrendGranularity, TrendMetric } from '@/types/api'

const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)

export default function AnalyticsTrafficPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const [granularity, setGranularity] = useState<TrendGranularity>('hour')
  const [trendMetric, setTrendMetric] = useState<TrendMetric>('bytes')
  const [heatmapBlocked, setHeatmapBlocked] = useState(false)

  const codes = useResultCodes(rangeParams, granularity, true)
  const rt = useResponseTime(rangeParams, granularity, true)
  const trend = useCategoryTrend(rangeParams, granularity === 'day' ? 'day' : 'hour', trendMetric, true)
  const heatmap = useActivityHeatmap(rangeParams, heatmapBlocked, true)

  const granularityToggle = (
    <Toggle
      value={granularity}
      onChange={setGranularity}
      options={[
        { value: 'hour', labelKey: 'analytics.trend.granularityHour' },
        { value: 'day', labelKey: 'analytics.trend.granularityDay' },
      ]}
    />
  )

  return (
    <div className="flex flex-col gap-4">
      <OpsRetentionNote />

      <Panel
        title={t('analytics.trend.title')}
        action={
          <Toggle
            value={trendMetric}
            onChange={setTrendMetric}
            options={[
              { value: 'bytes', labelKey: 'analytics.trend.metricBytes' },
              { value: 'requests', labelKey: 'analytics.trend.metricRequests' },
            ]}
          />
        }
      >
        <PanelErrorBoundary panelLabel={t('analytics.trend.title')}>
          {trend.isError ? (
            <ErrorState message={trend.error?.message} onRetry={() => trend.refetch()} />
          ) : (
            <div className="flex flex-col gap-4">
              <CategoryTrendChart data={trend.data} loading={trend.isLoading} />
              {trend.data && <CategoryBreakdownList data={trend.data} rangeParams={rangeParams} />}
            </div>
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('analytics.traffic.resultCodes')} action={granularityToggle}>
        <PanelErrorBoundary panelLabel={t('analytics.traffic.resultCodes')}>
          {codes.isError ? (
            <ErrorState message={codes.error?.message} onRetry={() => codes.refetch()} />
          ) : (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-3 gap-2">
                <MiniStat label={t('analytics.traffic.hitRatio')} value={pct(codes.data?.hit_ratio)} />
                <MiniStat label={t('analytics.traffic.byteHitRatio')} value={pct(codes.data?.byte_hit_ratio)} />
                <MiniStat
                  label={t('analytics.traffic.deniedRatio')}
                  value={pct(codes.data?.denied_ratio)}
                  tone={codes.data && codes.data.denied_ratio >= 0.1 ? 'warn' : 'default'}
                />
              </div>
              <StackedAreaOverTime
                rows={codes.data?.series ?? []}
                labels={codes.data?.series_labels ?? []}
                granularity={codes.data?.granularity ?? granularity}
                colorFor={resultCodeColor}
                loading={codes.isLoading}
                emptyText={t('analytics.trend.empty')}
              />
              <BreakdownBars items={codes.data?.codes ?? []} loading={codes.isLoading} barColor={resultCodeColor} />
            </div>
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel
        title={t('analytics.traffic.responseTime')}
        action={
          rt.data ? (
            <span className="font-data text-xs text-muted-foreground">
              p50 {ms(rt.data.overall_p50)} · p95 {ms(rt.data.overall_p95)} · p99 {ms(rt.data.overall_p99)}
            </span>
          ) : null
        }
      >
        <PanelErrorBoundary panelLabel={t('analytics.traffic.responseTime')}>
          {rt.isError ? (
            <ErrorState message={rt.error?.message} onRetry={() => rt.refetch()} />
          ) : (
            <div className="flex flex-col gap-4">
              <ResponseTimeChart
                points={rt.data?.series ?? []}
                granularity={rt.data?.granularity ?? granularity}
                loading={rt.isLoading}
              />
              <BreakdownBars items={rt.data?.bands ?? []} loading={rt.isLoading} barColor={durationBandColor} />
            </div>
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel
        title={t('analytics.heatmap.title')}
        action={
          <Toggle
            value={heatmapBlocked ? 'blocked' : 'all'}
            onChange={(v) => setHeatmapBlocked(v === 'blocked')}
            options={[
              { value: 'all', labelKey: 'analytics.heatmap.allTraffic' },
              { value: 'blocked', labelKey: 'analytics.heatmap.blockedOnly' },
            ]}
          />
        }
      >
        <PanelErrorBoundary panelLabel={t('analytics.heatmap.title')}>
          {heatmap.isError ? (
            <ErrorState message={heatmap.error?.message} onRetry={() => heatmap.refetch()} />
          ) : (
            <ActivityHeatmap data={heatmap.data} loading={heatmap.isLoading} />
          )}
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
