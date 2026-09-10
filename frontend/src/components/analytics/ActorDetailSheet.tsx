import { toast } from 'sonner'
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { ChevronRight, ShieldQuestion } from 'lucide-react'
import { formatBytes, formatDateTime, formatNumber } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { downloadSubjectDossier } from '@/lib/api-client'
import { useAuthStore } from '@/lib/auth-store'
import { useActorDetail } from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'
import type { ActorRow } from '@/types/api'

interface ActorDetailSheetProps {
  actor: ActorRow | null
  rangeParams: Record<string, string>
  onOpenChange: (open: boolean) => void
}

export function ActorDetailSheet({ actor, rangeParams, onOpenChange }: ActorDetailSheetProps) {
  const { t } = useTranslation()
  const role = useAuthStore((state) => state.role)
  const query = useActorDetail(rangeParams, actor?.actor ?? null, actor?.is_user ?? true)
  const data = query.data

  const maxHour = Math.max(...(data?.hourly ?? [0]), 1)

  return (
    <Sheet open={actor !== null} onOpenChange={onOpenChange}>
      <SheetContent className="w-full sm:max-w-lg">
        <SheetHeader>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <SheetTitle className="font-data break-all">{actor?.actor}</SheetTitle>
              <SheetDescription>
                {actor?.is_user ? t('analytics.who.colUser') : t('analytics.who.colClientIp')}
              </SheetDescription>
            </div>
            {/* Full subject-access dossier (docs/PRODUCT.md #4) -- admin-only
                on the backend (it includes watchlist status); every
                generation is itself audited there. */}
            {role === 'admin' && actor && (
              <Tooltip>
                <TooltipTrigger asChild>
                  <Button
                    variant="outline"
                    size="sm"
                    className="h-7 shrink-0 gap-1.5 px-2 text-xs"
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
        </SheetHeader>

        <div className="flex flex-col gap-4 overflow-y-auto px-4 pb-6">
          {query.isLoading ? (
            <div className="h-40 animate-pulse rounded bg-muted" />
          ) : data ? (
            <>
              <div className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-4">
                <div className="flex flex-col">
                  <span className="text-[11px] uppercase text-muted-foreground">
                    {t('analytics.metric.totalRequests')}
                  </span>
                  <span className="font-data font-semibold">{formatNumber(data.request_count)}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[11px] uppercase text-muted-foreground">
                    {t('analytics.metric.blocked')}
                  </span>
                  <span className="font-data font-semibold text-destructive">
                    {formatNumber(data.blocked_count)}
                  </span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[11px] uppercase text-muted-foreground">
                    {t('analytics.metric.downloaded')}
                  </span>
                  <span className="font-data font-semibold">{formatBytes(data.total_bytes)}</span>
                </div>
                <div className="flex flex-col">
                  <span className="text-[11px] uppercase text-muted-foreground">
                    {t('analytics.metric.uploaded')}
                  </span>
                  <span className="font-data font-semibold">
                    {data.bytes_received > 0 ? formatBytes(data.bytes_received) : '—'}
                  </span>
                </div>
              </div>

              <div className="flex justify-between text-xs text-muted-foreground">
                <span>
                  {t('analytics.who.firstSeen')}:{' '}
                  {data.first_seen ? formatDateTime(data.first_seen) : '—'}
                </span>
                <span>
                  {t('analytics.who.lastSeen')}: {data.last_seen ? formatDateTime(data.last_seen) : '—'}
                </span>
              </div>

              <section>
                <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
                  {t('analytics.who.hourlyActivity')}
                </h3>
                <div className="flex h-16 items-end gap-0.5">
                  {data.hourly.map((v, hour) => (
                    <div
                      key={hour}
                      className="flex-1 rounded-t-[2px] bg-info/70"
                      style={{ height: `${Math.max(2, (v / maxHour) * 100)}%` }}
                      title={`${String(hour).padStart(2, '0')}:00 UTC — ${formatNumber(v)}`}
                    />
                  ))}
                </div>
              </section>

              <section>
                <h3 className="mb-1.5 text-xs font-semibold uppercase text-muted-foreground">
                  {t('analytics.overview.topCategories')}
                </h3>
                <ul className="flex flex-col divide-y divide-border">
                  {data.categories.slice(0, 8).map((c) => (
                    <li key={c.category}>
                      <details className="group">
                        <summary className="flex cursor-pointer list-none items-center gap-2 py-1.5 text-sm [&::-webkit-details-marker]:hidden">
                          <ChevronRight
                            className="h-3.5 w-3.5 shrink-0 text-muted-foreground transition-transform group-open:rotate-90"
                            aria-hidden="true"
                          />
                          <span
                            className="h-2 w-2 shrink-0 rounded-full"
                            style={{ backgroundColor: CATEGORY_COLORS[c.category] }}
                            aria-hidden="true"
                          />
                          <span className="min-w-0 flex-1 truncate">
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
                        <ul className="mb-1 ml-[6px] flex flex-col divide-y divide-border/40 border-l border-border pl-4">
                          {c.domains.map((d) => (
                            <li key={d.domain} className="flex items-center gap-2 py-1 text-xs">
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

              {data.denied_domains.length > 0 && (
                <section>
                  <h3 className="mb-1.5 text-xs font-semibold uppercase text-destructive">
                    {t('analytics.who.deniedDomains')}
                  </h3>
                  <ul className="flex flex-col divide-y divide-border">
                    {data.denied_domains.slice(0, 8).map((d) => (
                      <li key={d.domain} className="flex items-center gap-2 py-1.5 text-sm">
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
