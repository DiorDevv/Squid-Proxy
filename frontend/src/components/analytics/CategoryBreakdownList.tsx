import { useState } from 'react'
import { ChevronRight } from 'lucide-react'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { formatBytes, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useTopDomains } from '@/hooks/useTopDomains'
import { useTranslation } from '@/i18n'
import type { CategoryTrendResponse, DomainCategoryLabel } from '@/types/api'

/** The category totals for the selected range, each row expandable to the
 * domains that make it up (GET /api/top-domains?category=…). Sits under
 * CategoryTrendChart so "why is Shopping our biggest slice" is one click,
 * not a separate page. Domains are fetched lazily, only when a row opens. */
export function CategoryBreakdownList({
  data,
  rangeParams,
}: {
  data: CategoryTrendResponse
  rangeParams: Record<string, string>
}) {
  const { t } = useTranslation()
  const [open, setOpen] = useState<Set<string>>(new Set())

  const totals: Record<string, number> = {}
  for (const point of data.points) {
    for (const category of data.categories) {
      totals[category] = (totals[category] ?? 0) + (point.values[category] ?? 0)
    }
  }
  const ordered = [...data.categories]
    .filter((c) => (totals[c] ?? 0) > 0)
    .sort((a, b) => (totals[b] ?? 0) - (totals[a] ?? 0))
  if (ordered.length === 0) return null

  const fmt = data.metric === 'bytes' ? formatBytes : formatNumber
  const toggle = (category: string) =>
    setOpen((prev) => {
      const next = new Set(prev)
      if (next.has(category)) next.delete(category)
      else next.add(category)
      return next
    })

  return (
    <div>
      <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
        {t('analytics.trend.byCategory')}
      </h3>
      <ul className="flex flex-col divide-y divide-border">
        {ordered.map((category) => (
          <li key={category}>
            <button
              type="button"
              onClick={() => toggle(category)}
              className="flex w-full items-center gap-2 py-1.5 text-sm"
              aria-expanded={open.has(category)}
            >
              <ChevronRight
                className={cn(
                  'h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform',
                  open.has(category) && 'rotate-90',
                )}
                aria-hidden="true"
              />
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: CATEGORY_COLORS[category] }}
                aria-hidden="true"
              />
              <span className="min-w-0 flex-1 truncate text-left">
                {t(CATEGORY_LABEL_KEYS[category] ?? 'category.other')}
              </span>
              <span className="font-data text-xs text-muted-foreground">{fmt(totals[category] ?? 0)}</span>
            </button>
            {open.has(category) && <CategoryDomains category={category} rangeParams={rangeParams} />}
          </li>
        ))}
      </ul>
    </div>
  )
}

function CategoryDomains({
  category,
  rangeParams,
}: {
  category: DomainCategoryLabel
  rangeParams: Record<string, string>
}) {
  const { t } = useTranslation()
  const query = useTopDomains(rangeParams, 10, true, category)

  if (query.isLoading) {
    return <div className="my-1 ml-6 h-6 animate-pulse rounded bg-muted" />
  }
  const items = query.data?.items ?? []
  if (items.length === 0) {
    return (
      <div className="ml-6 py-1 text-xs text-muted-foreground">
        {t('analytics.trend.noDomainsInCategory')}
      </div>
    )
  }
  return (
    <ul className="mb-1 ml-[6px] flex flex-col divide-y divide-border/40 border-l border-border pl-4">
      {items.map((d) => (
        <li key={d.domain} className="flex items-center gap-2 py-1 text-xs">
          <span className="font-data min-w-0 flex-1 truncate">{d.domain}</span>
          {d.blocked_count > 0 && (
            <span className="font-data text-[11px] text-destructive">{formatNumber(d.blocked_count)} ✕</span>
          )}
          <span className="font-data text-[11px] text-muted-foreground">{formatNumber(d.request_count)}</span>
          <span className="font-data text-[11px] text-muted-foreground">{formatBytes(d.total_bytes)}</span>
        </li>
      ))}
    </ul>
  )
}
