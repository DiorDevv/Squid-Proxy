import { cn } from '@/lib/utils'
import { formatNumber } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { BranchBreakdownRow } from '@/types/api'

/** A compact "requests by branch" strip for the Analytics Overview -- the
 * fastest place to notice a branch that has gone quiet (0 requests in the
 * window) without opening the Branches tab. Only rendered when there is
 * more than one branch. */
export function BranchMiniBar({ rows }: { rows: BranchBreakdownRow[] }) {
  const { t } = useTranslation()
  const total = rows.reduce((sum, r) => sum + r.total_requests, 0)
  const ordered = [...rows].sort((a, b) => b.total_requests - a.total_requests)

  return (
    <ul className="flex flex-col gap-2">
      {ordered.map((row) => {
        const share = total > 0 ? row.total_requests / total : 0
        const dark = row.total_requests === 0
        const highBlocked = row.blocked_ratio >= 0.2
        return (
          <li key={row.branch} className="flex flex-col gap-1">
            <div className="flex items-center justify-between gap-2 text-sm">
              <span
                className={cn(
                  'min-w-0 flex-1 truncate font-medium',
                  dark ? 'text-destructive' : 'text-foreground',
                )}
              >
                {row.branch}
                {dark && <span className="ml-2 text-xs font-normal">{t('analytics.overview.branchDark')}</span>}
              </span>
              <span className="font-data shrink-0 text-xs text-muted-foreground">
                {formatNumber(row.total_requests)} · {(share * 100).toFixed(0)}%
                {highBlocked && (
                  <span className="ml-2 text-warning">
                    {(row.blocked_ratio * 100).toFixed(0)}% {t('analytics.metric.blocked').toLowerCase()}
                  </span>
                )}
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className={cn('h-full rounded-full', dark ? 'bg-destructive' : 'bg-primary')}
                style={{ width: `${Math.max(share * 100, dark ? 0 : 2)}%` }}
              />
            </div>
          </li>
        )
      })}
    </ul>
  )
}
