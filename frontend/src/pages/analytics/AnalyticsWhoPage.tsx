import { useState } from 'react'
import { toast } from 'sonner'
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight, Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { SearchFilterInput } from '@/components/common/SearchFilterInput'
import { ActorLeaderboard } from '@/components/analytics/ActorLeaderboard'
import { ActorDetailSheet } from '@/components/analytics/ActorDetailSheet'
import { formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { downloadActorList } from '@/lib/api-client'
import { isAdminRole, useAuthStore } from '@/lib/auth-store'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useActorLeaderboard, useNewEntities } from '@/hooks/useAnalytics'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { ActorKindFilter, ActorRow } from '@/types/api'

function NewList({ titleKey, items, total }: { titleKey: TranslationKey; items: string[]; total: number }) {
  const { t } = useTranslation()
  return (
    <div className="flex min-w-0 flex-col gap-1.5">
      <div className="flex items-baseline justify-between gap-2">
        <h3
          className="min-w-0 truncate text-xs font-semibold uppercase text-muted-foreground"
          title={t(titleKey)}
        >
          {t(titleKey)}
        </h3>
        <span className="font-data shrink-0 text-xs text-muted-foreground">{formatNumber(total)}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('analytics.who.noneNew')}</p>
      ) : (
        <ul className="scrollbar-thin flex max-h-48 flex-col gap-0.5 overflow-y-auto">
          {items.map((v) => (
            <li key={v} className="font-data truncate text-sm text-foreground" title={v}>
              {v}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

const PAGE_SIZES = [50, 100, 200]

const KIND_TABS: { kind: ActorKindFilter; labelKey: TranslationKey }[] = [
  { kind: 'all', labelKey: 'analytics.who.kindAll' },
  { kind: 'user', labelKey: 'analytics.who.kindUsers' },
  { kind: 'ip', labelKey: 'analytics.who.kindIps' },
]

function Pager({
  offset,
  limit,
  total,
  onOffsetChange,
  onLimitChange,
}: {
  offset: number
  limit: number
  total: number
  onOffsetChange: (offset: number) => void
  onLimitChange: (limit: number) => void
}) {
  const { t } = useTranslation()
  const page = Math.floor(offset / limit) + 1
  const totalPages = Math.max(1, Math.ceil(total / limit))
  const lastOffset = (totalPages - 1) * limit
  return (
    <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
      <span className="font-data">{t('common.pageOf', { page, totalPages, total: formatNumber(total) })}</span>
      <div className="flex items-center gap-2">
        <label className="flex items-center gap-1.5">
          {t('analytics.who.pageSize')}
          <select
            value={limit}
            onChange={(e) => onLimitChange(Number(e.target.value))}
            className="font-data h-7 rounded-md border border-border bg-background px-1.5 text-xs text-foreground"
          >
            {PAGE_SIZES.map((size) => (
              <option key={size} value={size}>
                {size}
              </option>
            ))}
          </select>
        </label>
        <div className="flex items-center gap-1">
          <Button variant="outline" size="icon-sm" disabled={offset === 0} onClick={() => onOffsetChange(0)}
            aria-label={t('analytics.who.firstPage')}>
            <ChevronsLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon-sm" disabled={offset === 0}
            onClick={() => onOffsetChange(Math.max(0, offset - limit))} aria-label={t('common.previousPage')}>
            <ChevronLeft className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon-sm" disabled={offset + limit >= total}
            onClick={() => onOffsetChange(offset + limit)} aria-label={t('common.nextPage')}>
            <ChevronRight className="h-4 w-4" />
          </Button>
          <Button variant="outline" size="icon-sm" disabled={offset >= lastOffset}
            onClick={() => onOffsetChange(lastOffset)} aria-label={t('analytics.who.lastPage')}>
            <ChevronsRight className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  )
}

export default function AnalyticsWhoPage() {
  const { t, locale } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const role = useAuthStore((state) => state.role)
  const canExport = isAdminRole(role) || role === 'auditor'
  const [sort, setSort] = useState('requests')
  const [selected, setSelected] = useState<ActorRow | null>(null)
  const [search, setSearch] = useState('')
  const [kind, setKind] = useState<ActorKindFilter>('all')
  const [limit, setLimit] = useState(50)
  const [exporting, setExporting] = useState<'xlsx' | 'csv' | null>(null)
  const debouncedSearch = useDebouncedValue(search, 300)

  // The page belongs to one list: any change to what's listed (range,
  // branch, sort, filter, page size, search) starts again from page 1 --
  // derived here rather than reset in an effect, which would first fetch
  // the new list at the old offset.
  const listKey = JSON.stringify([rangeParams, sort, kind, limit, debouncedSearch])
  const [page, setPage] = useState({ key: listKey, offset: 0 })
  const offset = page.key === listKey ? page.offset : 0
  const setOffset = (next: number) => setPage({ key: listKey, offset: next })

  const board = useActorLeaderboard(rangeParams, sort, limit, true, debouncedSearch, offset, kind)
  const newEntities = useNewEntities(rangeParams, true)
  const data = board.data

  async function exportList(format: 'xlsx' | 'csv') {
    setExporting(format)
    try {
      await downloadActorList(format, { ...rangeParams, sort, kind, lang: locale, search: debouncedSearch || undefined })
    } catch {
      toast.error(t('analytics.who.exportFailed'))
    } finally {
      setExporting(null)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('analytics.who.title')}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">{t('analytics.who.hint')}</span>
            <SearchFilterInput
              value={search}
              onChange={setSearch}
              placeholder={t('analytics.who.searchPlaceholder')}
              ariaLabel={t('analytics.who.searchAriaLabel')}
            />
            {canExport &&
              (['xlsx', 'csv'] as const).map((format) => (
                <Button
                  key={format}
                  variant="outline"
                  size="sm"
                  disabled={exporting !== null}
                  onClick={() => exportList(format)}
                  title={t('analytics.who.exportHint')}
                >
                  <Download className="h-3.5 w-3.5" />
                  {format === 'xlsx' ? 'Excel' : 'CSV'}
                </Button>
              ))}
          </div>
        }
      >
        <PanelErrorBoundary panelLabel={t('analytics.who.title')}>
          {board.isError ? (
            <ErrorState message={board.error?.message} onRetry={() => board.refetch()} />
          ) : (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div
                  role="tablist"
                  aria-label={t('analytics.who.kindFilterLabel')}
                  className="flex items-center gap-1 rounded-md bg-secondary/40 p-0.5"
                >
                  {KIND_TABS.map((tab) => {
                    const count =
                      tab.kind === 'user'
                        ? data?.user_count
                        : tab.kind === 'ip'
                          ? data?.ip_count
                          : data && data.user_count + data.ip_count
                    return (
                      <button
                        key={tab.kind}
                        type="button"
                        role="tab"
                        aria-selected={kind === tab.kind}
                        onClick={() => setKind(tab.kind)}
                        className={cn(
                          'rounded px-2.5 py-1 text-xs transition-colors',
                          kind === tab.kind
                            ? 'bg-background font-medium text-foreground shadow-sm'
                            : 'text-muted-foreground hover:text-foreground',
                        )}
                      >
                        {t(tab.labelKey)}
                        {count !== undefined && <span className="font-data ml-1.5 opacity-70">{formatNumber(count)}</span>}
                      </button>
                    )
                  })}
                </div>
                {data && (
                  <span className="font-data text-xs text-muted-foreground">
                    {t('analytics.who.totalSummary', {
                      total: formatNumber(data.user_count + data.ip_count),
                      users: formatNumber(data.user_count),
                      ips: formatNumber(data.ip_count),
                    })}
                  </span>
                )}
              </div>
              {(data?.unattributed_requests ?? 0) > 0 && (
                <p className="rounded-md bg-secondary/40 px-2.5 py-1.5 text-xs text-muted-foreground">
                  {t('analytics.who.unattributed', {
                    count: formatNumber(data?.unattributed_requests ?? 0),
                  })}
                </p>
              )}
              <ActorLeaderboard
                rows={data?.rows ?? []}
                actorKind={data?.actor_kind ?? 'user'}
                loading={board.isLoading}
                sort={sort}
                onSortChange={setSort}
                onSelect={setSelected}
                emptyMessage={debouncedSearch ? t('analytics.who.searchEmpty') : undefined}
                rankOffset={offset}
              />
              {data && data.total > PAGE_SIZES[0]! && (
                <Pager
                  offset={offset}
                  limit={limit}
                  total={data.total}
                  onOffsetChange={setOffset}
                  onLimitChange={setLimit}
                />
              )}
            </div>
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel
        title={t('analytics.who.newThisPeriod')}
        action={<span className="text-xs text-muted-foreground">{t('analytics.movers.hint')}</span>}
      >
        <PanelErrorBoundary panelLabel={t('analytics.who.newThisPeriod')}>
          {newEntities.isLoading ? (
            <div className="h-40 animate-pulse rounded bg-muted" />
          ) : (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-2">
              <NewList
                titleKey="analytics.who.newUsers"
                items={newEntities.data?.new_users ?? []}
                total={newEntities.data?.new_users_total ?? 0}
              />
              <NewList
                titleKey="analytics.who.newClients"
                items={newEntities.data?.new_clients ?? []}
                total={newEntities.data?.new_clients_total ?? 0}
              />
            </div>
          )}
        </PanelErrorBoundary>
      </Panel>

      <ActorDetailSheet
        actor={selected}
        rangeParams={rangeParams}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </div>
  )
}
