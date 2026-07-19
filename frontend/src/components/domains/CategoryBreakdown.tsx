import { EmptyState } from '@/components/common/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { formatBytes } from '@/lib/format'
import { CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { CategoryStat, DomainCategoryLabel } from '@/types/api'

interface CategoryBreakdownProps {
  items: CategoryStat[]
  isLoading: boolean
  selectedCategory?: DomainCategoryLabel | null
  onSelectCategory?: (category: DomainCategoryLabel | null) => void
}

export function CategoryBreakdown({ items, isLoading, selectedCategory, onSelectCategory }: CategoryBreakdownProps) {
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <div className="flex h-80 flex-col gap-2">
        {Array.from({ length: 7 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex h-80 items-center justify-center">
        <EmptyState message={t('domains.empty')} />
      </div>
    )
  }

  const max = Math.max(...items.map((item) => item.total_bytes), 1)

  return (
    <ol className="scrollbar-thin -mr-1 flex h-80 flex-col divide-y divide-border overflow-y-auto pr-1">
      {items.map((item) => {
        const isActive = selectedCategory === item.category
        return (
          <li
            key={item.category}
            className={cn(
              'flex flex-col gap-1 rounded-md px-1 py-2.5 text-sm transition-colors duration-150',
              onSelectCategory && 'cursor-pointer hover:bg-secondary/40',
              isActive && 'bg-secondary/60',
            )}
            onClick={() => onSelectCategory?.(isActive ? null : item.category)}
          >
            <div className="flex items-center gap-3">
              <span className="min-w-0 flex-1 truncate text-foreground">
                {t(CATEGORY_LABEL_KEYS[item.category])}
              </span>
              <span className="font-data shrink-0 text-xs text-accent-purple">
                {formatBytes(item.total_bytes)}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className="gradient-purple h-full rounded-full transition-[width] duration-500 ease-out"
                style={{ width: `${(item.total_bytes / max) * 100}%` }}
              />
            </div>
          </li>
        )
      })}
    </ol>
  )
}
