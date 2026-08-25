import type { LucideIcon } from 'lucide-react'
import { TrendingDown, TrendingUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatNumber } from '@/lib/format'
import { useCountUp } from '@/hooks/useCountUp'
import { Sparkline } from '@/components/common/Sparkline'

interface SummaryCardProps {
  label: string
  /** null means "no meaningful value for this range" (e.g. cache hit rate
   * with zero cacheable traffic) -- distinct from 0, which is a real
   * measured value. Renders as a dash instead of a misleading "0". */
  value: number | null
  icon: LucideIcon
  tone?: 'default' | 'warning' | 'success' | 'info' | 'purple'
  /** Shown as the dash's title/tooltip when value is null. */
  noDataLabel?: string
  loading?: boolean
  /** True while a background refetch (e.g. a new range) is in flight but a
   * previous value is still on screen -- dims the number instead of
   * replacing it with a skeleton, so switching ranges never looks like it
   * silently did nothing while the request is still in flight. */
  updating?: boolean
  formatValue?: (value: number) => string
  /** Percentage change vs. the equivalent previous period (e.g. +12.4 or
   * -8.1). null/undefined means "no comparison available" (still loading,
   * or the previous period had zero to divide by) -- the badge is simply
   * omitted rather than shown as "0%" or an error state. Purely directional
   * (up/down), not "good/bad" -- a rise in blocked requests isn't
   * necessarily worse than a fall, so tone stays neutral either way. */
  deltaPercent?: number | null
  /** Recent trend, oldest first (already downsampled by the caller -- see
   * DashboardPage). Omit when there's no per-bucket series for this metric
   * (e.g. active client count isn't in the timeseries response) to leave
   * the card exactly as it was before this existed, not an empty gap. */
  sparkline?: number[]
}

const SPARKLINE_COLOR: Record<NonNullable<SummaryCardProps['tone']>, string> = {
  default: 'var(--muted-foreground)',
  info: 'var(--info)',
  purple: 'var(--accent-purple)',
  success: 'var(--success)',
  warning: 'var(--warning)',
}

const TONE_STYLES: Record<
  NonNullable<SummaryCardProps['tone']>,
  { badge: string; icon: string; glow: string }
> = {
  default: {
    badge: 'bg-muted',
    icon: 'text-muted-foreground',
    glow: '',
  },
  info: {
    badge: 'gradient-info',
    icon: 'text-white',
    glow: 'shadow-[0_0_24px_-8px_var(--info)]',
  },
  purple: {
    badge: 'gradient-purple',
    icon: 'text-white',
    glow: 'shadow-[0_0_24px_-8px_var(--accent-purple)]',
  },
  success: {
    badge: 'gradient-success',
    icon: 'text-white',
    glow: 'shadow-[0_0_24px_-8px_var(--success)]',
  },
  warning: {
    badge: 'gradient-warning',
    icon: 'text-white',
    glow: 'shadow-[0_0_24px_-8px_var(--warning)]',
  },
}

export function SummaryCard({
  label,
  value,
  icon: Icon,
  tone = 'default',
  noDataLabel,
  loading,
  updating,
  formatValue = formatNumber,
  deltaPercent,
  sparkline,
}: SummaryCardProps) {
  const hasValue = value !== null
  const animated = useCountUp(value ?? 0)
  const styles = TONE_STYLES[tone]
  const delta = !loading && hasValue && typeof deltaPercent === 'number' ? deltaPercent : null

  return (
    <div className="group relative flex flex-col gap-3 overflow-hidden rounded-xl border border-border bg-card p-4 transition-all duration-200 hover:border-border/60 hover:shadow-lg">
      {/* Faint tone-colored wash in the corner -- a hint of color without
          competing with the number, which stays neutral foreground. */}
      <div
        className={cn(
          'pointer-events-none absolute -top-8 -right-8 h-24 w-24 rounded-full opacity-[0.07] blur-2xl transition-opacity duration-300 group-hover:opacity-[0.12]',
          styles.badge,
        )}
        aria-hidden="true"
      />
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
          {label}
        </span>
        <div
          className={cn(
            'flex h-8 w-8 items-center justify-center rounded-lg transition-shadow duration-200',
            styles.badge,
            styles.glow,
          )}
        >
          <Icon className={cn('h-4 w-4', styles.icon)} aria-hidden="true" />
        </div>
      </div>
      {loading ? (
        <div className="h-8 w-24 animate-pulse rounded bg-muted" />
      ) : (
        <div className="flex items-baseline gap-2">
          <span
            className={cn(
              'font-data text-3xl font-semibold tracking-tight text-foreground transition-opacity duration-200',
              !hasValue && 'text-muted-foreground',
              updating && 'opacity-50',
            )}
            title={!hasValue ? noDataLabel : undefined}
          >
            {hasValue ? formatValue(animated) : '—'}
          </span>
          {delta !== null && (
            <span
              className={cn(
                'flex items-center gap-0.5 text-xs font-medium transition-opacity duration-200',
                delta >= 0 ? 'text-success' : 'text-destructive',
                updating && 'opacity-50',
              )}
            >
              {delta >= 0 ? (
                <TrendingUp className="h-3 w-3" aria-hidden="true" />
              ) : (
                <TrendingDown className="h-3 w-3" aria-hidden="true" />
              )}
              {Math.abs(delta) < 1000 ? Math.abs(delta).toFixed(1) : '999+'}%
            </span>
          )}
        </div>
      )}
      {/* Fixed-height slot even without a sparkline (no per-bucket series
          for this metric, e.g. active clients) -- keeps every card in the
          row the same height instead of the ones with a trend growing
          taller than the one without. */}
      <div className="h-8">
        {!loading && sparkline && sparkline.length >= 2 && (
          <Sparkline values={sparkline} id={tone} color={SPARKLINE_COLOR[tone]} />
        )}
      </div>
    </div>
  )
}
