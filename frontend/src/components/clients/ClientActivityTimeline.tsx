import { Link } from 'react-router-dom'
import { StatusBadge } from '@/components/common/StatusBadge'
import { EmptyState } from '@/components/common/EmptyState'
import { Skeleton } from '@/components/ui/skeleton'
import { formatBytes, formatDateTime } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { ClientActivityEvent } from '@/types/api'

interface ClientActivityTimelineProps {
  events: ClientActivityEvent[]
  isLoading: boolean
}

export function ClientActivityTimeline({ events, isLoading }: ClientActivityTimelineProps) {
  const { t } = useTranslation()

  if (isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 8 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    )
  }

  if (events.length === 0) {
    return <EmptyState message={t('clientDetail.empty')} />
  }

  return (
    <ol className="scrollbar-thin -mr-1 flex h-[30rem] flex-col overflow-y-auto pr-1">
      {events.map((event, index) => (
        <li
          key={event.id}
          className="flex flex-wrap items-center gap-x-4 gap-y-1 border-l-2 border-border py-2 pl-4 text-xs relative"
        >
          <span
            className="absolute -left-[5px] top-3 h-2 w-2 rounded-full bg-border"
            aria-hidden="true"
          />
          <span className="font-data w-40 shrink-0 text-muted-foreground">{formatDateTime(event.timestamp)}</span>
          <span className="font-data w-14 shrink-0 text-foreground">{event.method}</span>
          {event.domain ? (
            <Link
              to={`/domains/${encodeURIComponent(event.domain)}`}
              className="min-w-0 flex-1 truncate text-foreground hover:text-primary hover:underline"
              title={event.url}
              onClick={(e) => e.stopPropagation()}
            >
              {event.domain}
            </Link>
          ) : (
            <span className="min-w-0 flex-1 truncate text-foreground" title={event.url}>
              {event.url}
            </span>
          )}
          <span className="font-data w-16 shrink-0 text-muted-foreground">{formatBytes(event.bytes)}</span>
          <StatusBadge blocked={event.blocked} />
          {index === events.length - 1 && <span className="sr-only">{t('clientDetail.endOfHistory')}</span>}
        </li>
      ))}
    </ol>
  )
}
