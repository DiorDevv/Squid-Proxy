import { useState } from 'react'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { StackedAreaOverTime } from '@/components/analytics/StackedAreaOverTime'
import { MiniStat } from '@/components/analytics/MiniStat'
import { Toggle } from '@/components/analytics/Toggle'
import { formatBytes, formatNumber } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { DENIAL_REASON_COLORS } from '@/lib/ops-colors'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useDenials } from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'
import type { TrendGranularity } from '@/types/api'

const REASON_LABEL_KEYS = {
  acl_denied: 'analytics.blocks.aclDenied',
  proxy_auth: 'analytics.blocks.proxyAuth',
  other_blocked: 'analytics.blocks.otherBlocked',
} as const

export default function AnalyticsBlocksPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const [granularity, setGranularity] = useState<TrendGranularity>('hour')
  const denials = useDenials(rangeParams, granularity, true)
  const d = denials.data

  const seriesRows = (d?.series ?? []).map((p) => ({
    bucket_ts: p.bucket_ts,
    values: {
      acl_denied: p.acl_denied,
      proxy_auth: p.proxy_auth,
      other_blocked: p.other_blocked,
    },
  }))

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('analytics.blocks.title')}
        action={
          <Toggle
            value={granularity}
            onChange={setGranularity}
            options={[
              { value: 'hour', labelKey: 'analytics.trend.granularityHour' },
              { value: 'day', labelKey: 'analytics.trend.granularityDay' },
            ]}
          />
        }
      >
        <PanelErrorBoundary panelLabel={t('analytics.blocks.title')}>
          {denials.isError ? (
            <ErrorState message={denials.error?.message} onRetry={() => denials.refetch()} />
          ) : (
            <div className="flex flex-col gap-4">
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <MiniStat
                  label={t('analytics.blocks.totalDenied')}
                  value={formatNumber(d?.total_denied ?? 0)}
                  tone="warn"
                />
                <MiniStat label={t('analytics.blocks.aclDenied')} value={formatNumber(d?.acl_denied ?? 0)} tone="bad" />
                <MiniStat label={t('analytics.blocks.proxyAuth')} value={formatNumber(d?.proxy_auth ?? 0)} />
                <MiniStat label={t('analytics.blocks.otherBlocked')} value={formatNumber(d?.other_blocked ?? 0)} />
              </div>
              <StackedAreaOverTime
                rows={seriesRows}
                labels={['acl_denied', 'proxy_auth', 'other_blocked']}
                granularity={d?.granularity ?? granularity}
                colorFor={(l) => DENIAL_REASON_COLORS[l as keyof typeof DENIAL_REASON_COLORS] ?? '#64748b'}
                labelFor={(l) => t(REASON_LABEL_KEYS[l as keyof typeof REASON_LABEL_KEYS])}
                loading={denials.isLoading}
                emptyText={t('analytics.blocks.empty')}
              />
            </div>
          )}
        </PanelErrorBoundary>
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <Panel title={t('analytics.blocks.topDomains')}>
          <PanelErrorBoundary panelLabel={t('analytics.blocks.topDomains')}>
            {denials.isLoading ? (
              <div className="h-40 animate-pulse rounded bg-muted" />
            ) : (d?.top_domains.length ?? 0) === 0 ? (
              <div className="py-6 text-center text-sm text-muted-foreground">{t('analytics.blocks.empty')}</div>
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {d?.top_domains.map((row) => (
                  <li key={row.domain} className="flex items-center gap-2 py-1.5 text-sm">
                    <span className="font-data min-w-0 flex-1 truncate text-destructive">{row.domain}</span>
                    <span className="font-data text-xs text-muted-foreground">{formatNumber(row.blocked_count)}</span>
                  </li>
                ))}
              </ul>
            )}
          </PanelErrorBoundary>
        </Panel>

        <Panel title={t('analytics.blocks.topCategories')}>
          <PanelErrorBoundary panelLabel={t('analytics.blocks.topCategories')}>
            {denials.isLoading ? (
              <div className="h-40 animate-pulse rounded bg-muted" />
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {(d?.top_categories ?? []).map((c) => (
                  <li key={c.category} className="flex items-center gap-2 py-1.5 text-sm">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: CATEGORY_COLORS[c.category] }}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1 truncate">{t(CATEGORY_LABEL_KEYS[c.category])}</span>
                    <span className="font-data text-xs text-muted-foreground">{formatNumber(c.request_count)}</span>
                    <span className="font-data text-xs text-muted-foreground opacity-60">
                      {formatBytes(c.total_bytes)}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </PanelErrorBoundary>
        </Panel>

        <Panel title={t('analytics.blocks.repeatOffenders')}>
          <PanelErrorBoundary panelLabel={t('analytics.blocks.repeatOffenders')}>
            {denials.isLoading ? (
              <div className="h-40 animate-pulse rounded bg-muted" />
            ) : (
              <ul className="flex flex-col divide-y divide-border">
                {(d?.top_actors ?? []).map((a) => (
                  <li key={a.actor} className="flex items-center gap-2 py-1.5 text-sm">
                    <span className="font-data min-w-0 flex-1 truncate">{a.actor}</span>
                    <span className="font-data text-xs text-destructive">{formatNumber(a.blocked_count)}</span>
                  </li>
                ))}
              </ul>
            )}
          </PanelErrorBoundary>
        </Panel>
      </div>
    </div>
  )
}
