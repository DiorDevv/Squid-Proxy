import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { StackedAreaOverTime } from '@/components/analytics/StackedAreaOverTime'
import { MiniStat } from '@/components/analytics/MiniStat'
import { Toggle } from '@/components/analytics/Toggle'
import { OpsRetentionNote } from '@/components/analytics/OpsRetentionNote'
import { formatBytes, formatNumber } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { DENIAL_REASON_COLORS } from '@/lib/ops-colors'
import { cn } from '@/lib/utils'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useDenials } from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'
import type { ActorCategorySlice, TrendGranularity } from '@/types/api'

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
      <OpsRetentionNote />
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
              <p className="text-xs text-muted-foreground">{t('analytics.blocks.reasonNote')}</p>
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
                  <BlockedCategoryRow key={c.category} slice={c} />
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

/** One row of the Blocks "Top categories" panel -- expands to the blocked
 * domains that fell under this category (already in the denials response,
 * no extra request). */
function BlockedCategoryRow({ slice }: { slice: ActorCategorySlice }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  return (
    <li>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-2 py-1.5 text-sm"
        aria-expanded={open}
      >
        <ChevronRight
          className={cn(
            'h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform',
            open && 'rotate-90',
          )}
          aria-hidden="true"
        />
        <span
          className="h-2 w-2 shrink-0 rounded-full"
          style={{ backgroundColor: CATEGORY_COLORS[slice.category] }}
          aria-hidden="true"
        />
        <span className="min-w-0 flex-1 truncate text-left">{t(CATEGORY_LABEL_KEYS[slice.category])}</span>
        <span className="font-data text-xs text-muted-foreground">{formatNumber(slice.request_count)}</span>
        <span className="font-data text-xs text-muted-foreground opacity-60">{formatBytes(slice.total_bytes)}</span>
      </button>
      {open && slice.domains.length > 0 && (
        <ul className="mb-1 ml-[6px] flex flex-col divide-y divide-border/40 border-l border-border pl-4">
          {slice.domains.map((dom) => (
            <li key={dom.domain} className="flex items-center gap-2 py-1 text-xs">
              <span className="font-data min-w-0 flex-1 truncate text-destructive">{dom.domain}</span>
              <span className="font-data text-[11px] text-muted-foreground">
                {formatNumber(dom.blocked_count)}
              </span>
            </li>
          ))}
        </ul>
      )}
    </li>
  )
}
