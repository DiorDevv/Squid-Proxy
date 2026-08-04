import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { SortingState } from '@tanstack/react-table'
import { toast } from 'sonner'
import { ArrowLeft, Activity, Database, Info, ShieldX, Users } from 'lucide-react'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { RangeSelector } from '@/components/common/RangeSelector'
import { DomainClientsTable } from '@/components/domains/DomainClientsTable'
import { SummaryCard } from '@/components/dashboard/SummaryCard'
import { useDomainClients, useDomainSummary } from '@/hooks/useDomainDetail'
import { useSetDomainCategory } from '@/hooks/useDomainCategories'
import { useRangeSearchParams } from '@/lib/filters-store'
import { formatBytes, formatNumber } from '@/lib/format'
import { CATEGORY_LABEL_KEYS, CATEGORY_OPTIONS } from '@/lib/categories'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { DomainCategoryLabel } from '@/types/api'

const LIMIT = 25

export default function DomainDetailPage() {
  const { t } = useTranslation()
  const { domain } = useParams<{ domain: string }>()
  const [offset, setOffset] = useState(0)
  const [sorting, setSorting] = useState<SortingState>([{ id: 'visit_count', desc: true }])

  const sortBy = sorting[0]?.id ?? 'visit_count'
  const order = sorting[0]?.desc === false ? 'asc' : 'desc'

  const rangeParams = useRangeSearchParams()
  const summaryQuery = useDomainSummary(domain, rangeParams)
  const clientsQuery = useDomainClients({
    domain,
    rangeParams,
    limit: LIMIT,
    offset,
    sortBy,
    order,
  })
  const setCategory = useSetDomainCategory()

  function handleCategoryChange(category: DomainCategoryLabel) {
    if (!domain) return
    setCategory.mutate(
      { domain, category },
      { onError: () => toast.error(t('common.errorDefault')) },
    )
  }

  const summary = summaryQuery.data
  const isEmptyRange = summaryQuery.isSuccess && summary?.total_requests === 0

  // A narrower range can leave `offset` pointing past the new total (see
  // the identical fix on ClientDetailPage) -- reset during render rather
  // than an effect, to avoid an extra cascading render.
  const pageResetKey = `${domain}|${sortBy}|${order}|${JSON.stringify(rangeParams)}`
  const [prevPageResetKey, setPrevPageResetKey] = useState(pageResetKey)
  if (pageResetKey !== prevPageResetKey) {
    setPrevPageResetKey(pageResetKey)
    setOffset(0)
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <Button variant="outline" size="icon-sm" asChild>
            <Link to="/domains" aria-label={t('domainDetail.back')}>
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <h1 className="font-data text-lg font-semibold text-foreground">{domain}</h1>
          {summary && (
            <Select
              value={summary.category}
              onValueChange={(value) => handleCategoryChange(value as DomainCategoryLabel)}
            >
              <SelectTrigger size="sm" className="w-40" aria-label={t('domainDetail.category')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {CATEGORY_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {t(CATEGORY_LABEL_KEYS[option])}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          )}
        </div>
        <RangeSelector />
      </div>

      {isEmptyRange && (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
          <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t('common.noDataForRange')}
        </div>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <SummaryCard
          label={t('domainDetail.totalVisits')}
          value={summary?.total_requests ?? 0}
          icon={Activity}
          tone="info"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
        />
        <SummaryCard
          label={t('domainDetail.distinctClients')}
          value={summary?.distinct_client_count ?? 0}
          icon={Users}
          tone="purple"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
        />
        <SummaryCard
          label={t('clientDetail.totalBlocked')}
          value={summary?.blocked_requests ?? 0}
          icon={ShieldX}
          tone="warning"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
        />
        <SummaryCard
          label={t('clientDetail.totalData')}
          value={summary?.total_bytes ?? 0}
          icon={Database}
          tone="success"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
          formatValue={formatBytes}
        />
      </div>

      <Panel
        title={t('domainDetail.clientsTitle')}
        action={
          clientsQuery.data && (
            <span
              className={cn(
                'font-data text-xs text-muted-foreground transition-opacity duration-200',
                clientsQuery.isFetching && 'opacity-50',
              )}
            >
              {t('domainDetail.matchingClients', { count: formatNumber(clientsQuery.data.total) })}
            </span>
          )
        }
      >
        <PanelErrorBoundary panelLabel={t('domainDetail.clientsTitle')}>
          {clientsQuery.isError ? (
            <ErrorState
              message={clientsQuery.error?.message}
              onRetry={() => clientsQuery.refetch()}
            />
          ) : (
            <DomainClientsTable
              items={clientsQuery.data?.items ?? []}
              total={clientsQuery.data?.total ?? 0}
              limit={LIMIT}
              offset={offset}
              onOffsetChange={setOffset}
              sorting={sorting}
              onSortingChange={setSorting}
              isLoading={clientsQuery.isLoading}
            />
          )}
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
