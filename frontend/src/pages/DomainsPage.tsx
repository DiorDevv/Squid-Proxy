import { useState } from 'react'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { RangeSelector } from '@/components/common/RangeSelector'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { DomainRankingTable } from '@/components/domains/DomainRankingTable'
import { CategoryBreakdown } from '@/components/domains/CategoryBreakdown'
import { useTopBlocked, useTopDataUsage, useTopDomains } from '@/hooks/useTopDomains'
import { useUsageByCategory } from '@/hooks/useDomainCategories'
import { useRangeSearchParams } from '@/lib/filters-store'
import { CATEGORY_LABEL_KEYS, CATEGORY_OPTIONS } from '@/lib/categories'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useTranslation } from '@/i18n'
import type { DomainCategoryLabel } from '@/types/api'

const ALL_CATEGORIES = 'all'

export default function DomainsPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const { connectionState } = useLiveEvents()
  const live = connectionState === 'open'

  const [category, setCategory] = useState<DomainCategoryLabel | null>(null)

  const topDomains = useTopDomains(rangeParams, 20, live, category)
  const topBlocked = useTopBlocked(rangeParams, 20, live, category)
  const topDataUsage = useTopDataUsage(rangeParams, 20, live, category)
  // The "by category" breakdown itself always shows every category
  // regardless of the filter above -- it's what the filter is driven from,
  // not something the filter should narrow down to one row.
  const byCategory = useUsageByCategory(rangeParams, live)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <Select
          value={category ?? ALL_CATEGORIES}
          onValueChange={(value) => setCategory(value === ALL_CATEGORIES ? null : (value as DomainCategoryLabel))}
        >
          <SelectTrigger size="sm" className="w-44" aria-label={t('domains.categoryFilter')}>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL_CATEGORIES}>{t('domains.allCategories')}</SelectItem>
            {CATEGORY_OPTIONS.map((option) => (
              <SelectItem key={option} value={option}>
                {t(CATEGORY_LABEL_KEYS[option])}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <RangeSelector />
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title={t('domains.mostVisited')}>
          {topDomains.isError ? (
            <ErrorState message={topDomains.error?.message} onRetry={() => topDomains.refetch()} />
          ) : (
            <DomainRankingTable
              items={topDomains.data?.items ?? []}
              isLoading={topDomains.isLoading}
              emphasize="request_count"
            />
          )}
        </Panel>
        <Panel title={t('domains.mostBlocked')}>
          {topBlocked.isError ? (
            <ErrorState message={topBlocked.error?.message} onRetry={() => topBlocked.refetch()} />
          ) : (
            <DomainRankingTable
              items={topBlocked.data?.items ?? []}
              isLoading={topBlocked.isLoading}
              emphasize="blocked_count"
            />
          )}
        </Panel>
        <Panel title={t('domains.mostDataUsage')}>
          {topDataUsage.isError ? (
            <ErrorState message={topDataUsage.error?.message} onRetry={() => topDataUsage.refetch()} />
          ) : (
            <DomainRankingTable
              items={topDataUsage.data?.items ?? []}
              isLoading={topDataUsage.isLoading}
              emphasize="total_bytes"
            />
          )}
        </Panel>
        <Panel title={t('domains.byCategory')}>
          {byCategory.isError ? (
            <ErrorState message={byCategory.error?.message} onRetry={() => byCategory.refetch()} />
          ) : (
            <CategoryBreakdown
              items={byCategory.data?.items ?? []}
              isLoading={byCategory.isLoading}
              selectedCategory={category}
              onSelectCategory={setCategory}
            />
          )}
        </Panel>
      </div>
    </div>
  )
}
