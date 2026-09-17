import { toast } from 'sonner'
import { useNavigate } from 'react-router-dom'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { SummaryCard } from '@/components/dashboard/SummaryCard'
import {
  Activity,
  CalendarClock,
  ChevronRight,
  Clock,
  Download,
  Eye,
  ExternalLink,
  Layers,
  ShieldQuestion,
  ShieldX,
  Upload,
} from 'lucide-react'
import { formatBytes, formatDateTime, formatNumber } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { downloadSubjectDossier } from '@/lib/api-client'
import { useAuthStore } from '@/lib/auth-store'
import { useFiltersStore } from '@/lib/filters-store'
import { useActorDetail } from '@/hooks/useAnalytics'
import { isWatchlistConflict, useCreateWatchlistEntry, useDeleteWatchlistEntry, useWatchlist } from '@/hooks/useWatchlist'
import { useTranslation } from '@/i18n'
import type { ActorRow } from '@/types/api'

interface ActorDetailSheetProps {
  actor: ActorRow | null
  rangeParams: Record<string, string>
  onOpenChange: (open: boolean) => void
}

const HOUR_TICKS = [0, 6, 12, 18, 23]

export function ActorDetailSheet({ actor, rangeParams, onOpenChange }: ActorDetailSheetProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()
  const role = useAuthStore((state) => state.role)
  const setPendingEventsSearch = useFiltersStore((state) => state.setPendingEventsSearch)
  const query = useActorDetail(rangeParams, actor?.actor ?? null, actor?.is_user ?? true)
  const data = query.data

  // Admin-only (backend enforces it too) -- lets an admin watch a suspicious
  // actor right from the investigation view instead of retyping its value
  // into Settings > Watchlist.
  const watchlistQuery = useWatchlist(role === 'admin')
  const createWatch = useCreateWatchlistEntry()
  const deleteWatch = useDeleteWatchlistEntry()
  const watchEntry = actor
    ? watchlistQuery.data?.find(
        (e) => e.target_type === (actor.is_user ? 'user' : 'client_ip') && e.value === actor.actor,
      )
    : undefined

  function toggleWatch() {
    if (!actor) return
    if (watchEntry) {
      deleteWatch.mutate(watchEntry.id, {
        onError: () => toast.error(t('analytics.who.watchlistUpdateFailed')),
      })
    } else {
      createWatch.mutate(
        {
          target_type: actor.is_user ? 'user' : 'client_ip',
          value: actor.actor,
          branch: rangeParams.branch ?? '',
        },
        {
          onError: (err) => {
            // Someone else already watched it between our check and this
            // click -- that's the state we wanted, not a failure.
            if (isWatchlistConflict(err)) watchlistQuery.refetch()
            else toast.error(t('analytics.who.watchlistUpdateFailed'))
          },
        },
      )
    }
  }

  const maxHour = Math.max(...(data?.hourly ?? [0]), 1)
  const blockedBytesTotal = data ? data.blocked_bytes + data.blocked_bytes_received : 0

  return (
    <Sheet open={actor !== null} onOpenChange={onOpenChange}>
      {/* Widened from max-w-lg -- five stat cards plus nested category/domain
          rows need real room; at the old width everything was cramped
          two-per-line with truncated labels. */}
      <SheetContent className="flex w-full flex-col data-[side=right]:sm:max-w-2xl">
        <SheetHeader>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <SheetTitle className="font-data text-lg break-all">{actor?.actor}</SheetTitle>
              <SheetDescription>
                {actor?.is_user ? t('analytics.who.colUser') : t('analytics.who.colClientIp')}
              </SheetDescription>
            </div>
            <div className="flex shrink-0 items-center gap-1.5">
              {actor && (
                <Button
                  variant="outline"
                  size="sm"
                  className="h-8 gap-1.5 px-2.5 text-xs"
                  onClick={() => {
                    setPendingEventsSearch(actor.actor)
                    navigate('/events')
                  }}
                >
                  <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('analytics.who.viewAllEvents')}
                </Button>
              )}
              {role === 'admin' && actor && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className={
                        watchEntry
                          ? 'h-8 gap-1.5 border-success/30 bg-success/15 px-2.5 text-xs text-success hover:bg-success/25'
                          : 'h-8 gap-1.5 px-2.5 text-xs'
                      }
                      disabled={watchlistQuery.isLoading || createWatch.isPending || deleteWatch.isPending}
                      onClick={toggleWatch}
                    >
                      <Eye className="h-3.5 w-3.5" aria-hidden="true" />
                      {watchEntry ? t('analytics.who.watching') : t('analytics.who.watch')}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>
                    {watchEntry ? t('analytics.who.watchingHint') : t('analytics.who.watchHint')}
                  </TooltipContent>
                </Tooltip>
              )}
              {/* Full subject-access dossier (docs/PRODUCT.md #4) -- admin-only
                  on the backend (it includes watchlist status); every
                  generation is itself audited there. */}
              {role === 'admin' && actor && (
                <Tooltip>
                  <TooltipTrigger asChild>
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-8 gap-1.5 px-2.5 text-xs"
                      onClick={() => {
                        downloadSubjectDossier(actor.is_user ? 'user' : 'client_ip', actor.actor).catch(() =>
                          toast.error(t('analytics.who.dossierDownloadFailed')),
                        )
                      }}
                    >
                      <ShieldQuestion className="h-3.5 w-3.5" aria-hidden="true" />
                      {t('analytics.who.downloadDossier')}
                    </Button>
                  </TooltipTrigger>
                  <TooltipContent>{t('analytics.who.downloadDossierHint')}</TooltipContent>
                </Tooltip>
              )}
            </div>
          </div>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-4 pb-8">
          {query.isLoading ? (
            <div className="grid grid-cols-2 gap-3">
              {Array.from({ length: 5 }).map((_, i) => (
                <div
                  key={i}
                  className={`h-28 animate-pulse rounded-xl bg-muted ${i === 4 ? 'col-span-2' : ''}`}
                />
              ))}
            </div>
          ) : data ? (
            <>
              <div className="grid grid-cols-2 gap-3">
                <SummaryCard
                  label={t('analytics.metric.totalRequests')}
                  value={data.request_count}
                  deltaPercent={data.request_count_pct_change}
                  icon={Activity}
                  tone="info"
                  formatValue={formatNumber}
                />
                <SummaryCard
                  label={t('analytics.metric.blocked')}
                  value={data.blocked_count}
                  deltaPercent={data.blocked_count_pct_change}
                  icon={ShieldX}
                  tone="warning"
                  formatValue={formatNumber}
                />
                <SummaryCard
                  label={t('analytics.metric.downloaded')}
                  value={data.total_bytes}
                  deltaPercent={data.total_bytes_pct_change}
                  icon={Download}
                  tone="purple"
                  formatValue={formatBytes}
                />
                <SummaryCard
                  label={t('analytics.metric.uploaded')}
                  value={data.bytes_received > 0 ? data.bytes_received : null}
                  deltaPercent={data.bytes_received_pct_change}
                  icon={Upload}
                  tone="purple"
                  formatValue={formatBytes}
                />
                {/* Bytes excluded from Downloaded/Uploaded above (a blocked
                    request's denial-page size, not real content) -- its own
                    card so nothing silently disappears, not netted out.
                    col-span-2: the odd one out in a 2-column grid of 5 --
                    full-width instead of leaving a lopsided empty cell next
                    to it. */}
                <div className="col-span-2">
                  <SummaryCard
                    label={t('analytics.metric.blockedBytes')}
                    value={blockedBytesTotal > 0 ? blockedBytesTotal : null}
                    deltaPercent={data.blocked_bytes_pct_change}
                    icon={ShieldX}
                    tone="warning"
                    formatValue={formatBytes}
                  />
                </div>
              </div>

              <div className="flex flex-wrap items-center gap-x-6 gap-y-1.5 rounded-xl border border-border bg-card px-4 py-3 text-sm">
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <CalendarClock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  {t('analytics.who.firstSeen')}:{' '}
                  <span className="font-data text-foreground">
                    {data.first_seen ? formatDateTime(data.first_seen) : '—'}
                  </span>
                </span>
                <span className="flex items-center gap-1.5 text-muted-foreground">
                  <CalendarClock className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                  {t('analytics.who.lastSeen')}:{' '}
                  <span className="font-data text-foreground">
                    {data.last_seen ? formatDateTime(data.last_seen) : '—'}
                  </span>
                </span>
              </div>

              <section className="rounded-xl border border-border bg-card p-4">
                <h3 className="mb-3 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Clock className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('analytics.who.hourlyActivity')}
                </h3>
                <div className="flex h-20 items-end gap-0.5">
                  {data.hourly.map((v, hour) => (
                    <div
                      key={hour}
                      className="flex-1 rounded-t-[3px] bg-info/70 transition-colors hover:bg-info"
                      style={{ height: `${Math.max(2, (v / maxHour) * 100)}%` }}
                      title={`${String(hour).padStart(2, '0')}:00 UTC — ${formatNumber(v)}`}
                    />
                  ))}
                </div>
                <div className="mt-1.5 flex justify-between font-data text-[10px] text-muted-foreground">
                  {HOUR_TICKS.map((h) => (
                    <span key={h}>{String(h).padStart(2, '0')}</span>
                  ))}
                </div>
              </section>

              <section className="rounded-xl border border-border bg-card p-4">
                <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  <Layers className="h-3.5 w-3.5" aria-hidden="true" />
                  {t('analytics.overview.topCategories')}
                </h3>
                <ul className="flex flex-col divide-y divide-border">
                  {data.categories.slice(0, 8).map((c) => (
                    <li key={c.category}>
                      <details className="group">
                        <summary className="-mx-2 flex cursor-pointer list-none items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted/50 [&::-webkit-details-marker]:hidden">
                          <ChevronRight
                            className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-90"
                            aria-hidden="true"
                          />
                          <span
                            className="h-2.5 w-2.5 shrink-0 rounded-full"
                            style={{ backgroundColor: CATEGORY_COLORS[c.category] }}
                            aria-hidden="true"
                          />
                          <span className="min-w-0 flex-1 truncate font-medium">
                            {t(CATEGORY_LABEL_KEYS[c.category])}
                          </span>
                          <span className="font-data text-xs text-muted-foreground">
                            {formatNumber(c.request_count)}
                          </span>
                          <span className="font-data text-xs text-muted-foreground">
                            {formatBytes(c.total_bytes)}
                            {c.bytes_received > 0 && (
                              <span className="text-info"> ↑{formatBytes(c.bytes_received)}</span>
                            )}
                          </span>
                        </summary>
                        <ul className="mb-1.5 ml-[10px] flex flex-col divide-y divide-border/40 border-l border-border pl-4">
                          {c.domains.map((d) => (
                            <li key={d.domain} className="flex items-center gap-2 py-1.5 text-xs">
                              <span className="font-data min-w-0 flex-1 truncate">{d.domain}</span>
                              {d.blocked_count > 0 && (
                                <span className="font-data text-[11px] text-destructive">
                                  {formatNumber(d.blocked_count)} ✕
                                </span>
                              )}
                              <span className="font-data text-[11px] text-muted-foreground">
                                {formatNumber(d.request_count)}
                              </span>
                              <span className="font-data text-[11px] text-muted-foreground">
                                {formatBytes(d.total_bytes)}
                                {d.bytes_received > 0 && (
                                  <span className="text-info"> ↑{formatBytes(d.bytes_received)}</span>
                                )}
                              </span>
                            </li>
                          ))}
                        </ul>
                      </details>
                    </li>
                  ))}
                </ul>
              </section>

              {data.top_domains.length > 0 && (
                <section className="rounded-xl border border-border bg-card p-4">
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                    <Layers className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('analytics.overview.topDomains')}
                  </h3>
                  <ul className="flex flex-col divide-y divide-border">
                    {data.top_domains.slice(0, 8).map((d) => (
                      <li
                        key={d.domain}
                        className="-mx-2 flex items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors hover:bg-muted/50"
                      >
                        <span
                          className="h-2.5 w-2.5 shrink-0 rounded-full"
                          style={{ backgroundColor: CATEGORY_COLORS[d.category] }}
                          aria-hidden="true"
                        />
                        <span className="font-data min-w-0 flex-1 truncate">{d.domain}</span>
                        {d.blocked_count > 0 && (
                          <span className="font-data text-xs text-destructive">
                            {formatNumber(d.blocked_count)} ✕
                          </span>
                        )}
                        <span className="font-data text-xs text-muted-foreground">
                          {formatNumber(d.request_count)}
                        </span>
                        <span className="font-data text-xs text-muted-foreground">
                          {formatBytes(d.total_bytes)}
                          {d.bytes_received > 0 && (
                            <span className="text-info"> ↑{formatBytes(d.bytes_received)}</span>
                          )}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}

              {data.denied_domains.length > 0 && (
                <section className="rounded-xl border border-destructive/30 bg-destructive/[0.04] p-4">
                  <h3 className="mb-2 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-destructive">
                    <ShieldX className="h-3.5 w-3.5" aria-hidden="true" />
                    {t('analytics.who.deniedDomains')}
                  </h3>
                  <ul className="flex flex-col divide-y divide-destructive/15">
                    {data.denied_domains.slice(0, 8).map((d) => (
                      <li
                        key={d.domain}
                        className="-mx-2 flex items-center gap-2 rounded-md px-2 py-2 text-sm transition-colors hover:bg-destructive/[0.06]"
                      >
                        <span className="font-data min-w-0 flex-1 truncate text-destructive">{d.domain}</span>
                        <span className="font-data text-xs text-muted-foreground">
                          {formatNumber(d.blocked_count)}
                        </span>
                      </li>
                    ))}
                  </ul>
                </section>
              )}
            </>
          ) : null}
        </div>
      </SheetContent>
    </Sheet>
  )
}
