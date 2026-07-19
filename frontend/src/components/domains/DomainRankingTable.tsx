import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { EmptyState } from '@/components/common/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { formatBytes, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { DomainStat } from '@/types/api'

type EmphasizeField = 'request_count' | 'blocked_count' | 'total_bytes'

interface DomainRankingTableProps {
  items: DomainStat[]
  isLoading: boolean
  emphasize: EmphasizeField
}

const BAR_GRADIENT: Record<EmphasizeField, string> = {
  request_count: 'gradient-info',
  blocked_count: 'gradient-warning',
  total_bytes: 'gradient-purple',
}

const VALUE_COLOR: Record<EmphasizeField, string> = {
  request_count: 'text-info',
  blocked_count: 'text-warning',
  total_bytes: 'text-accent-purple',
}

const RANK_BADGE: Record<EmphasizeField, string> = {
  request_count: 'bg-info/15 text-info',
  blocked_count: 'bg-warning/15 text-warning',
  total_bytes: 'bg-accent-purple/15 text-accent-purple',
}

export function DomainRankingTable({ items, isLoading, emphasize }: DomainRankingTableProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

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

  const max = Math.max(...items.map((item) => item[emphasize]), 1)
  const formatValue = emphasize === 'total_bytes' ? formatBytes : formatNumber

  return (
    <ol className="scrollbar-thin -mr-1 flex h-80 flex-col divide-y divide-border overflow-y-auto pr-1">
      {items.map((item, index) => (
        <li
          key={item.domain}
          className="group flex cursor-pointer items-center gap-3 rounded-md px-1 py-2.5 text-sm transition-colors duration-150 hover:bg-secondary/40"
          onClick={() => navigate(`/domains/${encodeURIComponent(item.domain)}`)}
        >
          <span
            className={cn(
              'font-data flex h-6 w-6 shrink-0 items-center justify-center rounded-md text-xs font-medium',
              index < 3 ? RANK_BADGE[emphasize] : 'bg-muted text-muted-foreground',
            )}
          >
            {index + 1}
          </span>
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex items-center gap-3">
              <span className="min-w-0 flex-1 truncate text-foreground" title={item.domain}>
                {item.domain}
              </span>
              <span className={cn('font-data shrink-0 text-xs', VALUE_COLOR[emphasize])}>
                {formatValue(item[emphasize])}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-muted">
              <div
                className={cn('h-full rounded-full transition-[width] duration-500 ease-out', BAR_GRADIENT[emphasize])}
                style={{ width: `${(item[emphasize] / max) * 100}%` }}
              />
            </div>
          </div>
          <ChevronRight
            className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity duration-150 group-hover:opacity-100"
            aria-hidden="true"
          />
        </li>
      ))}
    </ol>
  )
}
