import { useState } from 'react'
import { toast } from 'sonner'
import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { SearchFilterInput } from '@/components/common/SearchFilterInput'
import { RangeSelector } from '@/components/common/RangeSelector'
import { BranchSelector } from '@/components/common/BranchSelector'
import { SavedFiltersMenu } from '@/components/common/SavedFiltersMenu'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { BlockedEventsTable } from '@/components/blocked/BlockedEventsTable'
import { BlockFilterBar } from '@/components/blocked/BlockFilterBar'
import { BlockGroupsTable } from '@/components/blocked/BlockGroupsTable'
import { BlockSummaryCards } from '@/components/blocked/BlockSummaryCards'
import { EventDetailSheet } from '@/components/blocked/EventDetailSheet'
import { useEvents } from '@/hooks/useEvents'
import { useBlockGroups, useBlockSummary } from '@/hooks/useBlockedAnalysis'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { downloadBlockedGroups } from '@/lib/api-client'
import { isAdminRole, useAuthStore } from '@/lib/auth-store'
import {
  filterParams,
  GROUP_LABELS,
  useBlockPageState,
  type BlockOutcome,
  type BlockPagePatch,
} from '@/lib/block-filters'
import { useFiltersStore, useRangeSearchParams } from '@/lib/filters-store'
import { useTranslation, type TranslationKey } from '@/i18n'
import { cn } from '@/lib/utils'
import type { BlockGroupBy, BlockGroupRow, BlockGroupSort, BlockKind } from '@/types/api'
import type { LiveEvent } from '@/types/events'

const LIMIT = 50
const METHODS = ['GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'CONNECT']
const ALL_METHODS = 'all'
const GROUPS: BlockGroupBy[] = ['domain', 'client', 'user', 'subnet', 'branch', 'proxy']

const OUTCOMES: { value: BlockOutcome; labelKey: TranslationKey }[] = [
  { value: 'denied', labelKey: 'blocked.kind.denied' },
  { value: 'auth', labelKey: 'blocked.kind.auth' },
  { value: 'all', labelKey: 'blocked.kind.all' },
  { value: 'everything', labelKey: 'blocked.kind.everything' },
]

const SORTS: { value: BlockGroupSort; labelKey: TranslationKey; hiddenFor?: BlockGroupBy }[] = [
  { value: 'requests', labelKey: 'blocked.sort.requests' },
  { value: 'clients', labelKey: 'blocked.sort.clients', hiddenFor: 'client' },
  { value: 'users', labelKey: 'blocked.sort.users', hiddenFor: 'user' },
  { value: 'domains', labelKey: 'blocked.sort.domains', hiddenFor: 'domain' },
  { value: 'last', labelKey: 'blocked.sort.last' },
  { value: 'key', labelKey: 'blocked.sort.key' },
]

/** Where a click on a grouped row leads: that value becomes a filter and the
 * list regroups by the next useful dimension. null = not drillable. */
function drillDown(group: BlockGroupBy, key: string): BlockPagePatch | null {
  switch (group) {
    case 'domain':
      return { filters: { domains: `=${key}` }, group: 'client' }
    case 'client':
      return { filters: { clients: key }, group: 'domain' }
    case 'subnet':
      return { filters: { clients: key }, group: 'client' }
    case 'user':
      return { filters: { users: key ? `=${key}` : '-' }, group: 'domain' }
    case 'proxy':
      return key ? { filters: { proxy: key }, group: 'domain' } : null
    case 'branch':
      return { group: 'domain' }
  }
}

function Segmented<T extends string>({
  value,
  options,
  onChange,
  ariaLabel,
}: {
  value: T
  options: { value: T; label: string }[]
  onChange: (value: T) => void
  ariaLabel: string
}) {
  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      className="flex flex-wrap items-center gap-0.5 rounded-md border border-border bg-secondary/50 p-0.5"
    >
      {options.map((option) => (
        <button
          key={option.value}
          type="button"
          role="tab"
          aria-selected={value === option.value}
          onClick={() => onChange(option.value)}
          className={cn(
            'rounded-[calc(var(--radius-sm)-2px)] px-2 py-1 text-xs font-medium transition-colors duration-150',
            value === option.value ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {option.label}
        </button>
      ))}
    </div>
  )
}

export default function BlockedPage() {
  const { t, locale } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const setBranch = useFiltersStore((s) => s.setBranch)
  const { connectionState } = useLiveEvents()
  const live = connectionState === 'open'
  const role = useAuthStore((state) => state.role)
  const canExport = isAdminRole(role) || role === 'auditor'

  const { view, group, sort, outcome, filters, update } = useBlockPageState()
  // The aggregates only hold blocked requests.
  const kind: BlockKind = outcome === 'everything' ? 'denied' : outcome
  const blockedOnly = view === 'analysis' || outcome !== 'everything'

  // Requests-view-only extras
  const [method, setMethod] = useState(ALL_METHODS)
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 300)
  const [selectedEvent, setSelectedEvent] = useState<LiveEvent | null>(null)
  const [exporting, setExporting] = useState<string | null>(null)

  // Any change to what's listed starts again from page 1 -- derived rather
  // than reset in an effect, which would first fetch at the old offset.
  const listKey = JSON.stringify([view, rangeParams, outcome, filters, group, sort, method, debouncedSearch])
  const [page, setPage] = useState({ key: listKey, offset: 0 })
  const offset = page.key === listKey ? page.offset : 0
  const setOffset = (next: number) => setPage({ key: listKey, offset: next })

  const events = useEvents({
    rangeParams,
    limit: LIMIT,
    offset,
    blockedOnly,
    blockKind: blockedOnly ? kind : undefined,
    filters,
    method: method === ALL_METHODS ? undefined : method,
    search: debouncedSearch,
    live,
    enabled: view === 'requests',
  })
  // Fetched on both views: its proxy list feeds the shared filter bar.
  const summary = useBlockSummary({ rangeParams, filters, kind })
  const groups = useBlockGroups({
    rangeParams,
    filters,
    kind,
    group,
    sort,
    limit: LIMIT,
    offset,
    enabled: view === 'analysis',
  })

  function onRowClick(row: BlockGroupRow) {
    const next = drillDown(group, row.key)
    if (!next) return
    if (group === 'branch') setBranch(row.key)
    update(next, { push: true })
  }

  async function exportGroups(format: 'xlsx' | 'csv', columns: 'all' | 'key') {
    setExporting(`${format}-${columns}`)
    try {
      await downloadBlockedGroups(format, {
        ...rangeParams,
        ...filterParams(filters),
        columns,
        group,
        kind,
        sort,
        lang: locale,
      })
    } catch {
      toast.error(t('blocked.analysis.exportFailed'))
    } finally {
      setExporting(null)
    }
  }

  const outcomes = view === 'analysis' ? OUTCOMES.filter((o) => o.value !== 'everything') : OUTCOMES
  const sorts = SORTS.filter((s) => s.hiddenFor !== group)

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('blocked.title')}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <BranchSelector />
            <RangeSelector />
            <SavedFiltersMenu />
            <Segmented
              value={view}
              onChange={(next) => update({ view: next })}
              ariaLabel={t('blocked.viewLabel')}
              options={[
                { value: 'requests', label: t('blocked.viewRequests') },
                { value: 'analysis', label: t('blocked.viewAnalysis') },
              ]}
            />
            <Select
              value={view === 'analysis' ? kind : outcome}
              onValueChange={(v) => update({ outcome: v as BlockOutcome })}
            >
              <SelectTrigger size="sm" className="w-48" aria-label={t('blocked.kind.label')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {outcomes.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {t(option.labelKey)}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        }
      >
        <div className="flex flex-col gap-4">
          <BlockFilterBar
            filters={filters}
            proxies={summary.data?.available_proxies ?? []}
            onChange={(patch) => update({ filters: patch })}
          />

          {view === 'requests' ? (
            <div className="flex flex-col gap-2">
              <div className="flex flex-wrap items-center gap-2">
                <Select value={method} onValueChange={setMethod}>
                  <SelectTrigger size="sm" className="w-32" aria-label={t('blocked.methodFilter')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_METHODS}>{t('blocked.allMethods')}</SelectItem>
                    {METHODS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <SearchFilterInput
                  value={search}
                  onChange={setSearch}
                  placeholder={t('blocked.filterPlaceholder')}
                  ariaLabel={t('blocked.filterAriaLabel')}
                />
              </div>
              {events.isError ? (
                <ErrorState message={events.error?.message} onRetry={() => events.refetch()} />
              ) : (
                <BlockedEventsTable
                  items={events.data?.items ?? []}
                  total={events.data?.total ?? 0}
                  limit={LIMIT}
                  offset={offset}
                  onOffsetChange={setOffset}
                  isLoading={events.isLoading}
                  onRowClick={setSelectedEvent}
                  emptyMessage={
                    search.trim()
                      ? t('blocked.noMatch', { search: search.trim() })
                      : blockedOnly
                        ? t('blocked.emptyDefault')
                        : t('blocked.emptyDefaultAll')
                  }
                />
              )}
            </div>
          ) : (
            <div className="flex flex-col gap-4">
              {summary.isError ? (
                <ErrorState message={summary.error?.message} onRetry={() => summary.refetch()} />
              ) : (
                <BlockSummaryCards summary={summary.data} loading={summary.isFetching} />
              )}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="text-xs text-muted-foreground">{t('blocked.analysis.groupBy')}</span>
                  <Segmented
                    value={group}
                    onChange={(next) => update({ group: next })}
                    ariaLabel={t('blocked.analysis.groupBy')}
                    options={GROUPS.map((g) => ({ value: g, label: t(GROUP_LABELS[g]) }))}
                  />
                  <Select
                    value={sorts.some((s) => s.value === sort) ? sort : 'requests'}
                    onValueChange={(v) => update({ sort: v as BlockGroupSort })}
                  >
                    <SelectTrigger size="sm" className="w-40" aria-label={t('blocked.sort.label')}>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      {sorts.map((option) => (
                        <SelectItem key={option.value} value={option.value}>
                          {t(option.labelKey)}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
                {canExport && (
                  <div className="flex flex-wrap items-center gap-2">
                    {(
                      [
                        ['xlsx', 'all', 'Excel'],
                        ['csv', 'all', 'CSV'],
                        ['csv', 'key', t('blocked.analysis.exportKeys', { what: t(GROUP_LABELS[group]) })],
                      ] as const
                    ).map(([format, columns, label]) => (
                      <Button
                        key={`${format}-${columns}`}
                        variant="outline"
                        size="sm"
                        disabled={exporting !== null}
                        onClick={() => exportGroups(format, columns)}
                        title={columns === 'key' ? t('blocked.analysis.exportKeysHint') : undefined}
                      >
                        <Download className="h-3.5 w-3.5" />
                        {label}
                      </Button>
                    ))}
                  </div>
                )}
              </div>
              {groups.isError ? (
                <ErrorState message={groups.error?.message} onRetry={() => groups.refetch()} />
              ) : (
                <BlockGroupsTable
                  group={group}
                  items={groups.data?.items ?? []}
                  total={groups.data?.total ?? 0}
                  limit={LIMIT}
                  offset={offset}
                  onOffsetChange={setOffset}
                  isLoading={groups.isLoading}
                  onRowClick={onRowClick}
                />
              )}
              <p className="text-xs text-muted-foreground">{t('blocked.analysis.note')}</p>
            </div>
          )}
        </div>
      </Panel>
      <EventDetailSheet event={selectedEvent} onOpenChange={(open) => !open && setSelectedEvent(null)} />
    </div>
  )
}
