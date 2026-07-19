import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { Skeleton } from '@/components/ui/skeleton'
import { formatDuration } from '@/lib/format'
import { useTimeSpent } from '@/hooks/useTimeSpent'
import { useTranslation } from '@/i18n'

interface TimeSpentByDomainProps {
  clientIp: string | undefined
  rangeParams: Record<string, string>
}

export function TimeSpentByDomain({ clientIp, rangeParams }: TimeSpentByDomainProps) {
  const { t } = useTranslation()
  const query = useTimeSpent(clientIp, rangeParams)

  if (query.isLoading) {
    return (
      <div className="flex h-[30rem] flex-col gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-8 w-full" />
        ))}
      </div>
    )
  }

  if (query.isError) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }

  const items = query.data?.items ?? []
  if (items.length === 0) {
    return (
      <div className="flex h-[30rem] items-center justify-center">
        <EmptyState message={t('clientDetail.timeSpentEmpty')} />
      </div>
    )
  }

  const max = Math.max(...items.map((item) => item.total_seconds), 1)

  return (
    <ol className="scrollbar-thin -mr-1 flex h-[30rem] flex-col divide-y divide-border overflow-y-auto pr-1">
      {items.map((item) => (
        <li key={item.domain} className="flex flex-col gap-1 rounded-md px-1 py-2.5 text-sm">
          <div className="flex items-center gap-3">
            <span className="min-w-0 flex-1 truncate text-foreground" title={item.domain}>
              {item.domain}
            </span>
            <span className="font-data shrink-0 text-xs text-info">{formatDuration(item.total_seconds)}</span>
          </div>
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div
              className="gradient-info h-full rounded-full transition-[width] duration-500 ease-out"
              style={{ width: `${(item.total_seconds / max) * 100}%` }}
            />
          </div>
        </li>
      ))}
    </ol>
  )
}
