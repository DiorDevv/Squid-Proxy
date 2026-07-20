import { useState } from 'react'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { SearchFilterInput } from '@/components/common/SearchFilterInput'
import { RangeSelector } from '@/components/common/RangeSelector'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { BlockedEventsTable } from '@/components/blocked/BlockedEventsTable'
import { EventDetailSheet } from '@/components/blocked/EventDetailSheet'
import { useEvents } from '@/hooks/useEvents'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useTranslation } from '@/i18n'
import type { LiveEvent } from '@/types/events'

const LIMIT = 50
const METHODS = ['GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'CONNECT']
const ALL_METHODS = 'all'

export default function BlockedPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const { connectionState } = useLiveEvents()
  const live = connectionState === 'open'

  const [offset, setOffset] = useState(0)
  const [search, setSearch] = useState('')
  const [method, setMethod] = useState(ALL_METHODS)
  const [selectedEvent, setSelectedEvent] = useState<LiveEvent | null>(null)
  const debouncedSearch = useDebouncedValue(search, 300)

  // Server-side filtering (see /api/events?search=...) keeps `total` and the
  // rows on screen in agreement -- filtering an already-paged result
  // locally would leave the pager showing an unfiltered total while the
  // table showed a filtered, possibly-empty page.
  const query = useEvents({
    rangeParams,
    limit: LIMIT,
    offset,
    blockedOnly: true,
    method: method === ALL_METHODS ? undefined : method,
    search: debouncedSearch,
    live,
  })

  const resetKey = `${debouncedSearch}|${method}|${JSON.stringify(rangeParams)}`
  const [prevResetKey, setPrevResetKey] = useState(resetKey)
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey)
    setOffset(0)
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('blocked.title')}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <RangeSelector />
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
            <SearchFilterInput
              value={search}
              onChange={setSearch}
              placeholder={t('blocked.filterPlaceholder')}
              ariaLabel={t('blocked.filterAriaLabel')}
            />
          </div>
        }
      >
        {query.isError ? (
          <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
        ) : (
          <BlockedEventsTable
            items={query.data?.items ?? []}
            total={query.data?.total ?? 0}
            limit={LIMIT}
            offset={offset}
            onOffsetChange={setOffset}
            isLoading={query.isLoading}
            onRowClick={setSelectedEvent}
            emptyMessage={
              search.trim() ? t('blocked.noMatch', { search: search.trim() }) : t('blocked.emptyDefault')
            }
          />
        )}
      </Panel>
      <EventDetailSheet event={selectedEvent} onOpenChange={(open) => !open && setSelectedEvent(null)} />
    </div>
  )
}
