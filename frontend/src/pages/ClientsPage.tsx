import { useState } from 'react'
import type { SortingState } from '@tanstack/react-table'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { SearchFilterInput } from '@/components/common/SearchFilterInput'
import { RangeSelector } from '@/components/common/RangeSelector'
import { BranchSelector } from '@/components/common/BranchSelector'
import { ClientsTable } from '@/components/clients/ClientsTable'
import { useClients } from '@/hooks/useClients'
import { useDebouncedValue } from '@/hooks/useDebouncedValue'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useTranslation } from '@/i18n'

const LIMIT = 25

export default function ClientsPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const { connectionState } = useLiveEvents()
  const live = connectionState === 'open'

  const [offset, setOffset] = useState(0)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'total_requests', desc: true }])
  const [search, setSearch] = useState('')
  const debouncedSearch = useDebouncedValue(search, 300)

  const sortBy = sorting[0]?.id ?? 'total_requests'
  const order = sorting[0]?.desc === false ? 'asc' : 'desc'

  // Search is applied server-side (see /api/clients?search=...) so `total`
  // and the rows on screen always agree -- filtering only the already-paged
  // result client-side would leave the pager showing an unfiltered total
  // while the table showed a filtered, possibly-empty page.
  const query = useClients({ rangeParams, limit: LIMIT, offset, sortBy, order, live, search: debouncedSearch })

  // A new search (or a changed sort/range) should always land on page 1;
  // otherwise a user filtering from page 3 could see an empty table with no
  // indication that matches exist earlier. Adjusted during render (React's
  // documented pattern for "reset state when a prop/dependency changes")
  // rather than in an effect, which would cause an extra cascading render.
  const resetKey = `${debouncedSearch}|${sortBy}|${order}|${JSON.stringify(rangeParams)}`
  const [prevResetKey, setPrevResetKey] = useState(resetKey)
  if (resetKey !== prevResetKey) {
    setPrevResetKey(resetKey)
    setOffset(0)
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('clients.title')}
        action={
          <div className="flex flex-wrap items-center gap-2">
            <BranchSelector />
            <RangeSelector />
            <SearchFilterInput
              value={search}
              onChange={setSearch}
              placeholder={t('clients.filterPlaceholder')}
              ariaLabel={t('clients.filterAriaLabel')}
            />
          </div>
        }
      >
        {query.isError ? (
          <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
        ) : (
          <ClientsTable
            items={query.data?.items ?? []}
            total={query.data?.total ?? 0}
            limit={LIMIT}
            offset={offset}
            onOffsetChange={setOffset}
            sorting={sorting}
            onSortingChange={setSorting}
            isLoading={query.isLoading}
          />
        )}
      </Panel>
    </div>
  )
}
