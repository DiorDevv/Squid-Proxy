import { useState } from 'react'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { ActivityHeatmap } from '@/components/analytics/ActivityHeatmap'
import { cn } from '@/lib/utils'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useActivityHeatmap } from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'

export default function AnalyticsHeatmapPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const [blockedOnly, setBlockedOnly] = useState(false)
  const query = useActivityHeatmap(rangeParams, blockedOnly, true)

  return (
    <Panel
      title={t('analytics.heatmap.title')}
      action={
        <div className="flex items-center gap-0.5 rounded-md border border-border bg-secondary/50 p-0.5">
          <button
            type="button"
            onClick={() => setBlockedOnly(false)}
            aria-pressed={!blockedOnly}
            className={cn(
              'rounded-[calc(var(--radius-sm)-2px)] px-2 py-1 text-xs font-medium transition-colors duration-150',
              !blockedOnly ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t('analytics.heatmap.allTraffic')}
          </button>
          <button
            type="button"
            onClick={() => setBlockedOnly(true)}
            aria-pressed={blockedOnly}
            className={cn(
              'rounded-[calc(var(--radius-sm)-2px)] px-2 py-1 text-xs font-medium transition-colors duration-150',
              blockedOnly ? 'bg-destructive text-white' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            {t('analytics.heatmap.blockedOnly')}
          </button>
        </div>
      }
    >
      <PanelErrorBoundary panelLabel={t('analytics.heatmap.title')}>
        {query.isError ? (
          <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
        ) : (
          <ActivityHeatmap data={query.data} loading={query.isLoading} />
        )}
      </PanelErrorBoundary>
    </Panel>
  )
}
