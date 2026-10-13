import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
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
import { BlockedDomainsTable } from '@/components/blocked/BlockedDomainsTable'
import { EventDetailSheet } from '@/components/blocked/EventDetailSheet'
import { useEvents } from '@/hooks/useEvents'
import { useBlockedDomains } from '@/hooks/useBlockedDomains'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { downloadBlockedDomains } from '@/lib/api-client'
import { isAdminRole, useAuthStore } from '@/lib/auth-store'
import { useRangeSearchParams } from '@/lib/filters-store'
import { formatNumber } from '@/lib/format'
import { useTranslation, type TranslationKey } from '@/i18n'
import { cn } from '@/lib/utils'
import type { BlockedDomainSort, BlockKind } from '@/types/api'
import type { LiveEvent } from '@/types/events'

const LIMIT = 50
const METHODS = ['GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'CONNECT']
const ALL_METHODS = 'all'
const ALL_PROXIES = 'all'

type View = 'requests' | 'domains'
// The requests view can also show every request, blocked or not.
type Outcome = BlockKind | 'everything'

const OUTCOMES: { value: Outcome; labelKey: TranslationKey }[] = [
  { value: 'denied', labelKey: 'blocked.kind.denied' },
  { value: 'auth', labelKey: 'blocked.kind.auth' },
  { value: 'all', labelKey: 'blocked.kind.all' },
  { value: 'everything', labelKey: 'blocked.kind.everything' },
]

const SORTS: { value: BlockedDomainSort; labelKey: TranslationKey }[] = [
  { value: 'requests', labelKey: 'blocked.domains.sortRequests' },
  { value: 'last', labelKey: 'blocked.domains.sortLast' },
  { value: 'domain', labelKey: 'blocked.domains.sortDomain' },
]

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
      className="flex items-center gap-0.5 rounded-md border border-border bg-secondary/50 p-0.5"
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
  const navigate = useNavigate()
  const rangeParams = useRangeSearchParams()
  const { connectionState } = useLiveEvents()
  const live = connectionState === 'open'
  const role = useAuthStore((state) => state.role)
  const canExport = isAdminRole(role) || role === 'auditor'

  const [searchParams, setSearchParams] = useSearchParams()
  const view: View = searchParams.get('view') === 'domains' ? 'domains' : 'requests'
  const setView = (next: View) =>
    setSearchParams(
      (prev) => {
        const params = new URLSearchParams(prev)
        if (next === 'domains') params.set('view', 'domains')
        else params.delete('view')
        return params
      },
      { replace: true },
    )

  // A real block is the default: a 407 is the proxy asking for a login.
  const [outcome, setOutcome] = useState<Outcome>('denied')
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 300)

  // requests view
  const [method, setMethod] = useState(ALL_METHODS)
  const [selectedEvent, setSelectedEvent] = useState<LiveEvent | null>(null)
  const blockedOnly = outcome !== 'everything'

  // domains view
  const domainKind: BlockKind = outcome === 'everything' ? 'denied' : outcome
  const [proxy, setProxy] = useState(ALL_PROXIES)
  const [sort, setSort] = useState<BlockedDomainSort>('requests')
  const [exporting, setExporting] = useState<string | null>(null)

  // Any change to what's listed starts again from page 1 -- derived rather
  // than reset in an effect, which would first fetch at the old offset.
  const listKey = JSON.stringify([view, rangeParams, outcome, debouncedSearch, method, proxy, sort])
  const [page, setPage] = useState({ key: listKey, offset: 0 })
  const offset = page.key === listKey ? page.offset : 0
  const setOffset = (next: number) => setPage({ key: listKey, offset: next })

  // Server-side filtering (see /api/events?search=...) keeps `total` and the
  // rows on screen in agreement -- filtering an already-paged result
  // locally would leave the pager showing an unfiltered total while the
  // table showed a filtered, possibly-empty page.
  const events = useEvents({
    rangeParams,
    limit: LIMIT,
    offset,
    blockedOnly,
    blockKind: blockedOnly ? outcome : undefined,
    method: method === ALL_METHODS ? undefined : method,
    search: debouncedSearch,
    live,
    enabled: view === 'requests',
  })
  const domains = useBlockedDomains({
    rangeParams,
    limit: LIMIT,
    offset,
    kind: domainKind,
    sort,
    proxy: proxy === ALL_PROXIES ? undefined : proxy,
    search: debouncedSearch,
    enabled: view === 'domains',
  })

  async function exportDomains(format: 'xlsx' | 'csv', columns: 'all' | 'domain') {
    setExporting(`${format}-${columns}`)
    try {
      await downloadBlockedDomains(format, {
        ...rangeParams,
        columns,
        kind: domainKind,
        sort,
        lang: locale,
        proxy: proxy === ALL_PROXIES ? undefined : proxy,
        search: debouncedSearch || undefined,
      })
    } catch {
      toast.error(t('blocked.domains.exportFailed'))
    } finally {
      setExporting(null)
    }
  }

  const outcomes = view === 'domains' ? OUTCOMES.filter((o) => o.value !== 'everything') : OUTCOMES
  const proxies = domains.data?.available_proxies ?? []

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
              onChange={setView}
              ariaLabel={t('blocked.viewLabel')}
              options={[
                { value: 'requests', label: t('blocked.viewRequests') },
                { value: 'domains', label: t('blocked.viewDomains') },
              ]}
            />
            <Select value={view === 'domains' ? domainKind : outcome} onValueChange={(v) => setOutcome(v as Outcome)}>
              <SelectTrigger size="sm" className="w-44" aria-label={t('blocked.kind.label')}>
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
            {view === 'requests' ? (
              <Select value={method} onValueChange={setMethod}>
                <SelectTrigger size="sm" className="w-28" aria-label={t('blocked.methodFilter')}>
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
            ) : (
              <>
                <Select value={proxy} onValueChange={setProxy}>
                  <SelectTrigger size="sm" className="w-36" aria-label={t('blocked.domains.proxyFilter')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_PROXIES}>{t('blocked.domains.allProxies')}</SelectItem>
                    {proxies.map((option) => (
                      <SelectItem key={option} value={option}>
                        {option}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <Select value={sort} onValueChange={(v) => setSort(v as BlockedDomainSort)}>
                  <SelectTrigger size="sm" className="w-36" aria-label={t('blocked.domains.sortLabel')}>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {SORTS.map((option) => (
                      <SelectItem key={option.value} value={option.value}>
                        {t(option.labelKey)}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </>
            )}
            <SearchFilterInput
              value={search}
              onChange={setSearch}
              placeholder={t(view === 'domains' ? 'blocked.domains.searchPlaceholder' : 'blocked.filterPlaceholder')}
              ariaLabel={t('blocked.filterAriaLabel')}
            />
          </div>
        }
      >
        {view === 'requests' ? (
          events.isError ? (
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
          )
        ) : domains.isError ? (
          <ErrorState message={domains.error?.message} onRetry={() => domains.refetch()} />
        ) : (
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <span className="font-data text-xs text-muted-foreground">
                {domains.data
                  ? t('blocked.domains.summary', {
                      domains: formatNumber(domains.data.total),
                      denied: formatNumber(domains.data.denied_total),
                      auth: formatNumber(domains.data.auth_total),
                    })
                  : ' '}
              </span>
              {canExport && (
                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={exporting !== null}
                    onClick={() => exportDomains('xlsx', 'all')}
                  >
                    <Download className="h-3.5 w-3.5" />
                    Excel
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={exporting !== null}
                    onClick={() => exportDomains('csv', 'all')}
                  >
                    <Download className="h-3.5 w-3.5" />
                    CSV
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={exporting !== null}
                    onClick={() => exportDomains('csv', 'domain')}
                    title={t('blocked.domains.exportNamesHint')}
                  >
                    <Download className="h-3.5 w-3.5" />
                    {t('blocked.domains.exportNames')}
                  </Button>
                </div>
              )}
            </div>
            <BlockedDomainsTable
              items={domains.data?.items ?? []}
              total={domains.data?.total ?? 0}
              limit={LIMIT}
              offset={offset}
              onOffsetChange={setOffset}
              isLoading={domains.isLoading}
              onRowClick={(row) => navigate(`/domains/${encodeURIComponent(row.domain)}`)}
              emptyMessage={
                search.trim() ? t('blocked.domains.noMatch', { search: search.trim() }) : t('blocked.domains.empty')
              }
            />
            <p className="text-xs text-muted-foreground">{t('blocked.domains.hourlyNote')}</p>
          </div>
        )}
      </Panel>
      <EventDetailSheet event={selectedEvent} onOpenChange={(open) => !open && setSelectedEvent(null)} />
    </div>
  )
}
