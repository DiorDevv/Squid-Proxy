import { ArrowDownRight, ArrowUpRight, Minus } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatBytes } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS, SENSITIVE_CATEGORIES } from '@/lib/categories'
import { useTranslation } from '@/i18n'
import type { CategoryMover } from '@/types/api'

interface TopMoversListProps {
  movers: CategoryMover[]
  loading?: boolean
}

/** Categories that shifted the most (by byte volume) between this range
 * and the range before it -- "what changed since last time." */
export function TopMoversList({ movers, loading }: TopMoversListProps) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-9 w-full animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  if (movers.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.movers.empty')}
      </div>
    )
  }

  return (
    <ul className="flex flex-col divide-y divide-border">
      {movers.map((mover) => {
        const delta = mover.current_bytes - mover.previous_bytes
        const up = delta > 0
        const flat = delta === 0
        const sensitive = SENSITIVE_CATEGORIES.includes(mover.category)
        return (
          <li key={mover.category} className="flex items-center gap-3 py-2.5 text-sm">
            <span
              className="h-2.5 w-2.5 shrink-0 rounded-full"
              style={{ backgroundColor: CATEGORY_COLORS[mover.category] }}
              aria-hidden="true"
            />
            <span className="min-w-0 flex-1 truncate text-foreground">
              {t(CATEGORY_LABEL_KEYS[mover.category])}
            </span>
            <span className="font-data shrink-0 text-xs text-muted-foreground">
              {formatBytes(mover.current_bytes)}
            </span>
            <span
              className={cn(
                'font-data flex shrink-0 items-center gap-0.5 text-xs font-medium',
                flat && 'text-muted-foreground',
                up && (sensitive ? 'text-destructive' : 'text-amber-500'),
                !up && !flat && 'text-success',
              )}
            >
              {flat ? (
                <Minus className="h-3 w-3" aria-hidden="true" />
              ) : up ? (
                <ArrowUpRight className="h-3 w-3" aria-hidden="true" />
              ) : (
                <ArrowDownRight className="h-3 w-3" aria-hidden="true" />
              )}
              {mover.pct_change === null
                ? t('analytics.movers.new')
                : `${Math.abs(mover.pct_change) < 1000 ? Math.abs(mover.pct_change).toFixed(0) : '999+'}%`}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
