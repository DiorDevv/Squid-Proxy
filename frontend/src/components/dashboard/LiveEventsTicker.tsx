import { cn } from '@/lib/utils'
import { formatTime } from '@/lib/format'
import { EmptyState } from '@/components/common/EmptyState'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useTranslation } from '@/i18n'

export function LiveEventsTicker() {
  const { t } = useTranslation()
  const { events, isLoading } = useLiveEvents()

  if (isLoading) {
    return (
      <div className="flex flex-col gap-1.5">
        {Array.from({ length: 6 }).map((_, i) => (
          <div key={i} className="h-9 w-full animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }

  if (events.length === 0) {
    return <EmptyState message={t('dashboard.liveEventsEmpty')} />
  }

  return (
    <ul className="flex max-h-96 flex-col gap-1 overflow-y-auto pr-1" aria-live="polite" aria-relevant="additions">
      {events.map((event, index) => (
        <li
          key={event.id}
          className={cn(
            'flex items-center gap-3 rounded-md border-l-2 bg-secondary/40 px-2.5 py-1.5 text-xs',
            event.blocked ? 'border-l-warning' : 'border-l-success/40',
            index === 0 && 'animate-in slide-in-from-top-2 fade-in duration-300',
          )}
        >
          <span className="font-data w-20 shrink-0 text-muted-foreground">
            {formatTime(event.timestamp)}
          </span>
          <span
            className={cn(
              'font-data w-16 shrink-0 font-semibold',
              event.blocked ? 'text-warning' : 'text-success',
            )}
          >
            {event.status_code}
          </span>
          <span className="font-data w-32 shrink-0 truncate text-foreground" title={event.client_ip}>
            {event.client_ip}
          </span>
          <span className="truncate text-foreground" title={event.domain ?? event.url}>
            {event.domain ?? event.url}
          </span>
          {event.user && (
            <span className="font-data ml-auto shrink-0 text-muted-foreground">{event.user}</span>
          )}
        </li>
      ))}
    </ul>
  )
}
