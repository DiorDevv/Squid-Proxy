import { cn } from '@/lib/utils'
import { formatBytes, formatNumber } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { NamedCount } from '@/types/api'

interface BreakdownBarsProps {
  items: NamedCount[]
  loading?: boolean
  /** cap the number of rows shown */
  limit?: number
  /** show the byte total instead of the request count on the right */
  showBytes?: boolean
  /** highlight a row whose label matches (case-insensitive substring) */
  emphasize?: (label: string) => boolean
  barColor?: (label: string) => string
}

const DEFAULT_BAR = 'var(--color-info)'

export function BreakdownBars({
  items,
  loading,
  limit = 12,
  showBytes = false,
  emphasize,
  barColor,
}: BreakdownBarsProps) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <div className="flex flex-col gap-1.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-8 w-full animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  const shown = items.slice(0, limit)
  if (shown.length === 0) {
    return <div className="py-6 text-center text-sm text-muted-foreground">{t('analytics.trend.empty')}</div>
  }
  const max = Math.max(...shown.map((i) => i.request_count), 1)

  return (
    <ul className="flex flex-col gap-1.5">
      {shown.map((item) => {
        const hot = emphasize?.(item.label) ?? false
        return (
          <li key={item.label} className="flex flex-col gap-1 text-sm">
            <div className="flex items-center gap-3">
              <span
                className={cn(
                  'font-data min-w-0 flex-1 truncate',
                  hot ? 'font-medium text-destructive' : 'text-foreground',
                )}
              >
                {item.label}
              </span>
              <span className="font-data shrink-0 text-xs text-muted-foreground">
                {showBytes ? formatBytes(item.total_bytes) : formatNumber(item.request_count)}
                <span className="ml-1.5 opacity-60">{item.pct.toFixed(1)}%</span>
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="h-full rounded-full transition-[width] duration-500 ease-out"
                style={{
                  width: `${(item.request_count / max) * 100}%`,
                  backgroundColor: hot
                    ? 'var(--color-destructive)'
                    : (barColor?.(item.label) ?? DEFAULT_BAR),
                }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}
