import { useState } from 'react'
import { Bell, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { EmptyState } from '@/components/common/EmptyState'
import { ErrorState } from '@/components/common/ErrorState'
import { cn } from '@/lib/utils'
import { formatRelativeTime } from '@/lib/format'
import { useRecentInsights } from '@/hooks/useInsights'
import { useNotificationsStore } from '@/lib/notifications-store'
import { useTranslation, type TranslationKey } from '@/i18n'
import { localizeAnomaly } from '@/lib/insights'
import type { AnomalySeverity } from '@/types/api'

const SEVERITY_STYLES: Record<AnomalySeverity, string> = {
  low: 'bg-muted text-muted-foreground',
  medium: 'bg-warning/15 text-warning',
  high: 'bg-warning/15 text-warning',
  critical: 'bg-destructive/15 text-destructive',
}

const SEVERITY_LABEL_KEYS: Record<AnomalySeverity, TranslationKey> = {
  low: 'insights.severityLow',
  medium: 'insights.severityMedium',
  high: 'insights.severityHigh',
  critical: 'insights.severityCritical',
}

const BELL_LIST_LIMIT = 20

/** Topbar bell — the same anomaly feed dashboard/InsightsPanel already
 * shows, but reachable from every page (not just Dashboard) and with an
 * unread-count badge so a new high-severity anomaly doesn't go unnoticed
 * just because the admin happens to be on the Clients page. "Unread" is
 * purely a client-side timestamp comparison (see notifications-store.ts's
 * docstring for why there's no backend-side read state) -- opening the
 * popover marks everything currently loaded as seen. */
export function NotificationBell() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const { data, isLoading, isError, error, refetch } = useRecentInsights(BELL_LIST_LIMIT)
  const lastSeenAt = useNotificationsStore((state) => state.lastSeenAt)
  const markAllSeen = useNotificationsStore((state) => state.markAllSeen)

  const items = data?.items ?? []
  // A filter over BELL_LIST_LIMIT (20) items is cheap enough every render
  // that memoizing it would just trade one kind of recomputation for the
  // bookkeeping of another -- data?.items already gets a stable reference
  // from TanStack Query between polls, so this doesn't even re-run when
  // nothing's actually changed.
  const unreadCount =
    lastSeenAt === null ? items.length : items.filter((item) => item.generated_at > lastSeenAt).length

  function handleOpenChange(next: boolean) {
    setOpen(next)
    const newest = items[0]
    if (next && newest) {
      // The newest item's timestamp, not "now" -- so an anomaly that lands
      // in the brief window between this popover opening and the next
      // poll tick still shows as unread next time, instead of being
      // silently marked seen by a clock reading it was never actually
      // shown for.
      markAllSeen(newest.generated_at)
    }
  }

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <Button
          variant="ghost"
          size="icon-sm"
          className="relative"
          aria-label={t('notifications.bellLabel')}
        >
          <Bell className="h-4 w-4" aria-hidden="true" />
          {unreadCount > 0 && (
            <span
              className="absolute top-0.5 right-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-destructive px-1 text-[10px] font-medium leading-none text-destructive-foreground"
              aria-hidden="true"
            >
              {unreadCount > 9 ? '9+' : unreadCount}
            </span>
          )}
        </Button>
      </PopoverTrigger>
      <PopoverContent align="end" className="w-80 p-0">
        <div className="border-b border-border px-3 py-2">
          <h2 className="text-sm font-semibold text-foreground">{t('notifications.title')}</h2>
        </div>
        <div className="max-h-96 overflow-y-auto p-2">
          {isLoading ? (
            <div className="flex flex-col gap-2 p-1">
              {Array.from({ length: 3 }).map((_, i) => (
                <div key={i} className="h-14 w-full animate-pulse rounded-md bg-muted" />
              ))}
            </div>
          ) : isError ? (
            <ErrorState message={error?.message} onRetry={() => refetch()} />
          ) : items.length === 0 ? (
            <EmptyState message={t('notifications.empty')} />
          ) : (
            <ul className="flex flex-col gap-2">
              {items.map((item) => {
                const { title, description } = localizeAnomaly(item, t)
                return (
                  <li
                    key={item.id}
                    className="flex flex-col gap-1 rounded-md border border-border bg-secondary/40 px-3 py-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex min-w-0 items-center gap-2">
                        <TriangleAlert className="h-3.5 w-3.5 shrink-0 text-warning" aria-hidden="true" />
                        <span className="truncate text-sm font-medium text-foreground">{title}</span>
                      </div>
                      <span
                        className={cn(
                          'shrink-0 rounded-full px-2 py-0.5 text-[10px] font-medium tracking-wide uppercase',
                          SEVERITY_STYLES[item.severity],
                        )}
                      >
                        {t(SEVERITY_LABEL_KEYS[item.severity])}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground">{description}</p>
                    <span className="font-data text-[10px] text-muted-foreground">
                      {formatRelativeTime(item.generated_at)}
                    </span>
                  </li>
                )
              })}
            </ul>
          )}
        </div>
      </PopoverContent>
    </Popover>
  )
}
