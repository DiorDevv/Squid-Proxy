import { formatBytes } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { useTranslation } from '@/i18n'
import type { BranchCategoryBreakdownResponse } from '@/types/api'

const TILES_PER_BRANCH = 6

interface BranchCategoryBreakdownGridProps {
  data?: BranchCategoryBreakdownResponse
  loading?: boolean
}

/** What each branch's traffic is actually going to, by category -- one
 * small bar-list per branch, sized by byte share. Answers "what" a branch
 * is doing, not just "how much", which the requests/bytes trend (see
 * BranchTrendGrid) and the snapshot comparison can't. */
export function BranchCategoryBreakdownGrid({ data, loading }: BranchCategoryBreakdownGridProps) {
  const { t } = useTranslation()

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
        const top = series.categories.slice(0, TILES_PER_BRANCH)
        const max = Math.max(...top.map((c) => c.total_bytes), 1)
        return (
          <div key={series.branch} className="rounded-lg border border-border p-3">
            <span className="mb-2 block truncate text-sm font-medium text-foreground" title={series.branch}>
              {series.branch}
            </span>
            {top.length === 0 ? (
              <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
                {t('analytics.branches.trendBranchEmpty')}
              </div>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {top.map((usage) => (
                  <li key={usage.category} className="flex flex-col gap-1">
                    <div className="flex items-center justify-between gap-2 text-xs">
                      <span className="flex min-w-0 items-center gap-1.5">
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: CATEGORY_COLORS[usage.category] }}
                          aria-hidden="true"
                        />
                        <span className="min-w-0 truncate text-foreground">
                          {t(CATEGORY_LABEL_KEYS[usage.category])}
                        </span>
                      </span>
                      <span className="font-data shrink-0 text-muted-foreground">
                        {formatBytes(usage.total_bytes)}
                      </span>
                    </div>
                    <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
                      <div
                        className="h-full rounded-full transition-[width] duration-500 ease-out"
                        style={{
                          width: `${(usage.total_bytes / max) * 100}%`,
                          backgroundColor: CATEGORY_COLORS[usage.category],
                        }}
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
