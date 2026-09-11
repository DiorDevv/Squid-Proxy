import { useNavigate } from 'react-router-dom'
import { formatNumber } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { BranchBlockedDomainsResponse } from '@/types/api'

interface BranchBlockedDomainsGridProps {
  data?: BranchBlockedDomainsResponse
  loading?: boolean
}

/** Top blocked domains per branch, side by side -- reveals policy/risk
 * differences between locations (one branch mostly hitting gambling sites,
 * another mostly ad trackers) that a combined top-blocked list averages
 * away. Mirrors the Dashboard's TopBlockedDomains bar-list, one per
 * branch. */
export function BranchBlockedDomainsGrid({ data, loading }: BranchBlockedDomainsGridProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-48 w-full animate-pulse rounded-md bg-muted" />
        ))}
      </div>
    )
  }

  if (!data || data.series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.branches.empty')}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {data.series.map((series) => {
        const max = Math.max(...series.domains.map((d) => d.blocked_count), 1)
        return (
          <div key={series.branch} className="rounded-lg border border-border p-3">
            <span className="mb-2 block truncate text-sm font-medium text-foreground" title={series.branch}>
              {series.branch}
            </span>
            {series.domains.length === 0 ? (
              <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
                {t('analytics.branches.blockedDomainsEmpty')}
              </div>
            ) : (
              <ul className="flex flex-col gap-1">
                {series.domains.map((d) => (
                  <li
                    key={d.domain}
                    className="group flex cursor-pointer flex-col gap-1 rounded-md px-1 py-1 transition-colors duration-150 hover:bg-secondary/40"
                    onClick={() => navigate(`/domains/${encodeURIComponent(d.domain)}`)}
                  >
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="font-data min-w-0 truncate text-foreground" title={d.domain}>
                        {d.domain}
                      </span>
                      <span className="font-data shrink-0 text-destructive">{formatNumber(d.blocked_count)}</span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="gradient-warning h-full rounded-full transition-[width] duration-500 ease-out"
                        style={{ width: `${(d.blocked_count / max) * 100}%` }}
                      />
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        )
      })}
    </div>
  )
}
