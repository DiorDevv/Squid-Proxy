import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { ComparisonCards } from '@/components/analytics/ComparisonCards'
import { ConfigAdvisorPanel } from '@/components/analytics/ConfigAdvisorPanel'
import { SquidHealthStrip } from '@/components/analytics/SquidHealthStrip'
import { TopMoversList } from '@/components/analytics/TopMoversList'
import { cn } from '@/lib/utils'
import { formatBytes, formatNumber } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS, SENSITIVE_CATEGORIES } from '@/lib/categories'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useAnalyticsOverview, useConfigAdvisor } from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'
import type { DomainUsage } from '@/types/api'

function DomainList({ items, valueOf }: { items: DomainUsage[]; valueOf: (item: DomainUsage) => string }) {
  const { t } = useTranslation()
  if (items.length === 0) {
    return <div className="py-6 text-center text-sm text-muted-foreground">{t('analytics.trend.empty')}</div>
  }
  return (
    <ul className="flex flex-col divide-y divide-border">
      {items.map((item) => (
        <li key={item.domain} className="flex items-center gap-3 py-2 text-sm">
          <span
            className="h-2 w-2 shrink-0 rounded-full"
            style={{ backgroundColor: CATEGORY_COLORS[item.category] }}
            aria-hidden="true"
          />
          <span className="min-w-0 flex-1 truncate text-foreground">{item.domain}</span>
          <span className="font-data shrink-0 text-xs text-muted-foreground">{valueOf(item)}</span>
        </li>
      ))}
    </ul>
  )
}

export default function AnalyticsOverviewPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const query = useAnalyticsOverview(rangeParams, true)
  const advisor = useConfigAdvisor(rangeParams, true)
  const data = query.data
  const findings = advisor.data?.findings ?? []

  if (query.isError) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }

  return (
    <div className="flex flex-col gap-4">
      <ComparisonCards metrics={data?.metrics ?? []} loading={query.isLoading} />

      <Panel title={t('analytics.overview.squidHealth')}>
        <PanelErrorBoundary panelLabel={t('analytics.overview.squidHealth')}>
          <SquidHealthStrip />
        </PanelErrorBoundary>
      </Panel>

      {findings.length > 0 && (
        <Panel
          title={t('analytics.advisor.title')}
          action={<span className="text-xs text-muted-foreground">{t('analytics.advisor.hint')}</span>}
        >
          <PanelErrorBoundary panelLabel={t('analytics.advisor.title')}>
            <ConfigAdvisorPanel findings={findings} />
          </PanelErrorBoundary>
        </Panel>
      )}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title={t('analytics.overview.topCategories')}>
          <PanelErrorBoundary panelLabel={t('analytics.overview.topCategories')}>
            {query.isLoading ? (
              <div className="h-48 animate-pulse rounded bg-muted" />
            ) : (data?.top_categories.length ?? 0) === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">{t('analytics.trend.empty')}</div>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {data?.top_categories.map((item) => {
                  const sensitive = SENSITIVE_CATEGORIES.includes(item.category)
                  return (
                    <li key={item.category} className="flex items-center gap-3 py-2 text-sm">
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: CATEGORY_COLORS[item.category] }}
                        aria-hidden="true"
                      />
                      <span
                        className={cn(
                          'min-w-0 flex-1 truncate',
                          sensitive ? 'font-medium text-destructive' : 'text-foreground',
                        )}
                      >
                        {t(CATEGORY_LABEL_KEYS[item.category])}
                      </span>
                      <span className="font-data shrink-0 text-xs text-muted-foreground">
                        {formatBytes(item.total_bytes)}
                      </span>
                    </li>
                  )
                })}
              </ul>
            )}
          </PanelErrorBoundary>
        </Panel>

        <Panel title={t('analytics.overview.topDomains')}>
          <PanelErrorBoundary panelLabel={t('analytics.overview.topDomains')}>
            {query.isLoading ? (
              <div className="h-48 animate-pulse rounded bg-muted" />
            ) : (
              <DomainList
                items={data?.top_domains ?? []}
                valueOf={(item) => formatNumber(item.request_count)}
              />
            )}
          </PanelErrorBoundary>
        </Panel>

        <Panel title={t('analytics.overview.topBlockedDomains')}>
          <PanelErrorBoundary panelLabel={t('analytics.overview.topBlockedDomains')}>
            {query.isLoading ? (
              <div className="h-48 animate-pulse rounded bg-muted" />
            ) : (
              <DomainList
                items={data?.top_blocked_domains ?? []}
                valueOf={(item) => formatNumber(item.blocked_count)}
              />
            )}
          </PanelErrorBoundary>
        </Panel>
      </div>

      <Panel title={t('analytics.overview.topMovers')}>
        <PanelErrorBoundary panelLabel={t('analytics.overview.topMovers')}>
          <TopMoversList movers={data?.top_movers ?? []} loading={query.isLoading} />
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
