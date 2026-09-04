import { useState } from 'react'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { CategoryTrendChart } from '@/components/analytics/CategoryTrendChart'
import { TopMoversList } from '@/components/analytics/TopMoversList'
import { cn } from '@/lib/utils'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useAnalyticsOverview, useCategoryTrend } from '@/hooks/useAnalytics'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { TrendGranularity, TrendMetric } from '@/types/api'

function Toggle<T extends string>({
  value,
  options,
  onChange,
}: {
  value: T
  options: { value: T; labelKey: TranslationKey }[]
  onChange: (value: T) => void
}) {
  const { t } = useTranslation()
  return (
    <div className="flex items-center gap-0.5 rounded-md border border-border bg-secondary/50 p-0.5">
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          onClick={() => onChange(option.value)}
          aria-pressed={value === option.value}
          className={cn(
            'rounded-[calc(var(--radius-sm)-2px)] px-2 py-1 text-xs font-medium transition-colors duration-150',
            value === option.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {t(option.labelKey)}
        </button>
      ))}
    </div>
  )
}

export default function AnalyticsCategoriesPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const [granularity, setGranularity] = useState<TrendGranularity>('hour')
  const [metric, setMetric] = useState<TrendMetric>('bytes')

  const trend = useCategoryTrend(rangeParams, granularity, metric, true)
  const overview = useAnalyticsOverview(rangeParams, true)

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('analytics.trend.title')}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <Toggle
              value={metric}
              onChange={setMetric}
              options={[
                { value: 'bytes', labelKey: 'analytics.trend.metricBytes' },
                { value: 'requests', labelKey: 'analytics.trend.metricRequests' },
              ]}
            />
            <Toggle
              value={granularity}
              onChange={setGranularity}
              options={[
                { value: 'hour', labelKey: 'analytics.trend.granularityHour' },
                { value: 'day', labelKey: 'analytics.trend.granularityDay' },
              ]}
            />
          </div>
        }
      >
        <PanelErrorBoundary panelLabel={t('analytics.trend.title')}>
          {trend.isError ? (
            <ErrorState message={trend.error?.message} onRetry={() => trend.refetch()} />
          ) : (
            <>
              {trend.data && trend.data.granularity !== granularity && (
                <p className="text-xs text-muted-foreground">{t('analytics.trend.coarsenedNote')}</p>
              )}
              <CategoryTrendChart data={trend.data} loading={trend.isLoading} />
            </>
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('analytics.overview.topMovers')} action={<span className="text-xs text-muted-foreground">{t('analytics.movers.hint')}</span>}>
        <PanelErrorBoundary panelLabel={t('analytics.overview.topMovers')}>
          {overview.isError ? (
            <ErrorState message={overview.error?.message} onRetry={() => overview.refetch()} />
          ) : (
            <TopMoversList movers={overview.data?.top_movers ?? []} loading={overview.isLoading} />
          )}
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
