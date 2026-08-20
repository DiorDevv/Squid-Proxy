import { TriangleAlert } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/format'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { useRecentInsights } from '@/hooks/useInsights'
import { useTranslation, type TranslationKey } from '@/i18n'
import { localizeAnomaly } from '@/lib/insights'
import type { AnomalySeverity } from '@/types/api'

const SEVERITY_STYLES: Record<AnomalySeverity, string> = {
  low: 'bg-muted text-muted-foreground',
  medium: 'bg-warning/15 text-warning',
  high: 'bg-warning/15 text-warning',
  critical: 'bg-destructive/15 text-destructive',
}

const SEVERITY_LABEL_KEYS: Record<AnomalySeverity, TranslationKey> = {
  low: 'insights.severityLow',
  medium: 'insights.severityMedium',
  high: 'insights.severityHigh',
  critical: 'insights.severityCritical',
}

interface InsightsPanelProps {
  /** Called with an anomaly's id when its row is clicked -- lets a parent
   * (DashboardPage) highlight/scroll to the matching marker on the traffic
   * chart. Omit to keep rows non-interactive. */
  onSelectInsight?: (id: string) => void
}

export function InsightsPanel({ onSelectInsight }: InsightsPanelProps) {
  const { t } = useTranslation()
  const { data, isLoading, isError, error, refetch } = useRecentInsights(10)

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-14 w-full animate-pulse rounded-md bg-muted" />
        ))}
      </div>
    )
  }

  if (isError) {
    return <ErrorState message={error?.message} onRetry={() => refetch()} />
  }

  const items = data?.items ?? []
  if (items.length === 0) {
    return <EmptyState message={t('dashboard.insightsEmpty')} />
  }

  return (
    <ul className="flex max-h-96 flex-col gap-2 overflow-y-auto pr-1">
      {items.map((item) => {
        const { title, description } = localizeAnomaly(item, t)
        return (
          <li
            key={item.id}
            onClick={onSelectInsight ? () => onSelectInsight(item.id) : undefined}
            className={cn(
              'flex flex-col gap-1 rounded-md border border-border bg-secondary/40 px-3 py-2',
              onSelectInsight && 'cursor-pointer transition-colors duration-150 hover:bg-secondary/70',
            )}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="flex min-w-0 items-center gap-2">
                <TriangleAlert className="h-3.5 w-3.5 shrink-0 text-warning" aria-hidden="true" />
                <span className="truncate text-sm font-medium text-foreground">{title}</span>
              </div>
              <span
                className={cn(
                  'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase',
                  SEVERITY_STYLES[item.severity],
                )}
              >
                {t(SEVERITY_LABEL_KEYS[item.severity])}
              </span>
            </div>
            <p className="text-xs text-muted-foreground">{description}</p>
            <span className="font-data text-[10px] text-muted-foreground">
              {formatRelativeTime(item.generated_at)}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
