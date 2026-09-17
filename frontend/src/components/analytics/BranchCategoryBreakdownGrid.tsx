import { formatBytes, formatNumber } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { useTranslation } from '@/i18n'
import type { BranchCategoryBreakdownResponse } from '@/types/api'

interface BranchCategoryBreakdownGridProps {
  data?: BranchCategoryBreakdownResponse
  loading?: boolean
}

/** What each branch's traffic is actually going to, by category -- every
 * category the branch has any traffic in (not a top-N sample), in a small
 * table per branch. Answers "what" a branch is doing, not just "how much",
 * which the requests/bytes trend (see BranchTrendGrid) and the snapshot
 * comparison can't. */
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
      {data.series.map((series) => (
        <div key={series.branch} className="rounded-lg border border-border p-3">
          <span className="mb-2 block truncate text-sm font-medium text-foreground" title={series.branch}>
            {series.branch}
          </span>
          {series.categories.length === 0 ? (
            <div className="flex h-24 items-center justify-center text-xs text-muted-foreground">
              {t('analytics.branches.trendBranchEmpty')}
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[280px] text-xs">
                <thead>
                  <tr className="border-b border-border text-left text-muted-foreground">
                    <th className="py-1.5 pr-2 font-medium">{t('analytics.branches.colCategory')}</th>
                    <th className="py-1.5 pr-2 text-right font-medium">{t('analytics.metric.totalRequests')}</th>
                    <th className="py-1.5 pr-2 text-right font-medium">{t('analytics.metric.downloaded')}</th>
                    <th className="py-1.5 text-right font-medium">{t('analytics.metric.uploaded')}</th>
                  </tr>
                </thead>
                <tbody>
                  {series.categories.map((usage) => (
                    <tr key={usage.category} className="border-b border-border/40 last:border-b-0">
                      <td className="py-1.5 pr-2">
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
                      </td>
                      <td className="font-data py-1.5 pr-2 text-right text-muted-foreground">
                        {formatNumber(usage.request_count)}
                      </td>
                      <td className="font-data py-1.5 pr-2 text-right text-foreground">
                        {formatBytes(usage.total_bytes)}
                      </td>
                      <td className="font-data py-1.5 text-right text-info">
                        {usage.bytes_received > 0 ? formatBytes(usage.bytes_received) : '—'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      ))}
    </div>
  )
}
