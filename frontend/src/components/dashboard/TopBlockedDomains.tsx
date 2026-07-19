import { useNavigate } from 'react-router-dom'
import { ChevronRight } from 'lucide-react'
import { formatNumber } from '@/lib/format'
import { EmptyState } from '@/components/common/EmptyState'
import { useTranslation } from '@/i18n'
import type { DomainStat } from '@/types/api'

interface TopBlockedDomainsProps {
  items: DomainStat[]
  loading?: boolean
}

export function TopBlockedDomains({ items, loading }: TopBlockedDomainsProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  if (loading) {
    return (
      <div className="flex h-80 flex-col gap-2.5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-9 w-full animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  if (items.length === 0) {
    return (
      <div className="flex h-80 items-center justify-center">
        <EmptyState message={t('dashboard.topBlockedEmpty')} />
      </div>
    )
  }

  const max = Math.max(...items.map((item) => item.blocked_count), 1)

  return (
    <ul className="scrollbar-thin -mr-1 flex h-80 flex-col gap-1 overflow-y-auto pr-1">
      {items.map((item) => (
        <li
          key={item.domain}
          className="group flex cursor-pointer items-center gap-2 rounded-md px-1 py-2 transition-colors duration-150 hover:bg-secondary/40"
          onClick={() => navigate(`/domains/${encodeURIComponent(item.domain)}`)}
        >
          <div className="flex min-w-0 flex-1 flex-col gap-1">
            <div className="flex items-center justify-between text-xs">
              <span className="font-data truncate text-foreground" title={item.domain}>
                {item.domain}
              </span>
              <span className="font-data shrink-0 text-warning">{formatNumber(item.blocked_count)}</span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted">
              <div
                className="gradient-warning h-full rounded-full transition-[width] duration-500 ease-out"
                style={{ width: `${(item.blocked_count / max) * 100}%` }}
              />
            </div>
          </div>
          <ChevronRight
            className="h-4 w-4 shrink-0 text-muted-foreground opacity-0 transition-opacity duration-150 group-hover:opacity-100"
            aria-hidden="true"
          />
        </li>
      ))}
    </ul>
  )
}
