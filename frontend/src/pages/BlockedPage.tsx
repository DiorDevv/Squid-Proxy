import { useMemo, useState } from 'react'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { SearchFilterInput } from '@/components/common/SearchFilterInput'
import { BlockedEventsTable } from '@/components/blocked/BlockedEventsTable'
import { useRecentEvents } from '@/hooks/useRecentEvents'
import { useTranslation } from '@/i18n'

const LIMIT = 200

export default function BlockedPage() {
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const query = useRecentEvents({ limit: LIMIT, blockedOnly: true })

  // Filtered client-side over the *entire* fetched window (not a server
  // page), so unlike ClientsPage there's no "total" from a different,
  // unfiltered query to fall out of sync with -- BlockedEventsTable always
  // reports its own filtered length as the total.
  const filtered = useMemo(() => {
    const items = query.data ?? []
    if (!search.trim()) return items
    const needle = search.trim().toLowerCase()
    return items.filter(
      (event) =>
        event.client_ip.toLowerCase().includes(needle) ||
        event.domain?.toLowerCase().includes(needle) ||
        event.user?.toLowerCase().includes(needle),
    )
  }, [query.data, search])

  return (
    <Panel
      title={t('blocked.title')}
      action={
        <SearchFilterInput
          value={search}
          onChange={setSearch}
          placeholder={t('blocked.filterPlaceholder')}
          ariaLabel={t('blocked.filterAriaLabel')}
        />
      }
    >
      {query.isError ? (
        <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
      ) : (
        <BlockedEventsTable
          items={filtered}
          isLoading={query.isLoading}
          emptyMessage={
            search.trim()
              ? t('blocked.noMatch', { search: search.trim() })
              : t('blocked.emptyDefault')
          }
        />
      )}
    </Panel>
  )
}
