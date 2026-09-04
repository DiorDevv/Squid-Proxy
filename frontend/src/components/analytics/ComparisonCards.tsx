import type { LucideIcon } from 'lucide-react'
import { Activity, Database, Gauge, ShieldCheck, ShieldX, Users } from 'lucide-react'
import { SummaryCard } from '@/components/dashboard/SummaryCard'
import { formatBytes, formatNumber } from '@/lib/format'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { MetricDelta } from '@/types/api'

interface MetricConfig {
  labelKey: TranslationKey
  icon: LucideIcon
  tone: 'info' | 'warning' | 'success' | 'purple' | 'default'
  format: (value: number) => string
  /** ratio metrics come from the API as 0..1 -- scale to a percent for display */
  scale?: number
}

const PERCENT = (value: number) => `${value.toFixed(1)}%`

const METRICS: Record<string, MetricConfig> = {
  total_requests: { labelKey: 'analytics.metric.totalRequests', icon: Activity, tone: 'info', format: formatNumber },
  blocked_requests: { labelKey: 'analytics.metric.blocked', icon: ShieldX, tone: 'warning', format: formatNumber },
  allowed_requests: { labelKey: 'analytics.metric.allowed', icon: ShieldCheck, tone: 'success', format: formatNumber },
  total_bytes: { labelKey: 'analytics.metric.dataTransferred', icon: Database, tone: 'purple', format: formatBytes },
  active_clients: { labelKey: 'analytics.metric.activeClients', icon: Users, tone: 'purple', format: formatNumber },
  blocked_ratio: { labelKey: 'analytics.metric.blockedRatio', icon: ShieldX, tone: 'warning', format: PERCENT, scale: 100 },
  cache_hit_ratio: { labelKey: 'analytics.metric.cacheHitRate', icon: Gauge, tone: 'default', format: PERCENT, scale: 100 },
}

// The five volume headline numbers. The two operational ratios
// (blocked_ratio, cache_hit_ratio) that get_overview also returns live in
// the "Squid health" strip right below this on the Overview tab, so they
// aren't duplicated here.
const ORDER = ['total_requests', 'blocked_requests', 'allowed_requests', 'total_bytes', 'active_clients']

interface ComparisonCardsProps {
  metrics: MetricDelta[]
  loading: boolean
}

/** The headline row: each metric for the selected range with its delta vs.
 * the equal-length range immediately before it (computed server-side, see
 * /api/analytics/overview). */
export function ComparisonCards({ metrics, loading }: ComparisonCardsProps) {
  const { t } = useTranslation()
  const byMetric = new Map(metrics.map((m) => [m.metric, m]))

  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
      {ORDER.map((key) => {
        const config = METRICS[key]
        if (!config) return null
        const delta = byMetric.get(key)
        const scale = config.scale ?? 1
        return (
          <SummaryCard
            key={key}
            label={t(config.labelKey)}
            value={delta ? delta.current * scale : 0}
            icon={config.icon}
            tone={config.tone}
            loading={loading}
            formatValue={config.format}
            deltaPercent={delta?.pct_change ?? null}
          />
        )
      })}
    </div>
  )
}
