import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, Activity, Database, Info, ShieldX } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { SearchFilterInput } from '@/components/common/SearchFilterInput'
import { RangeSelector } from '@/components/common/RangeSelector'
import { ClientActivityTimeline } from '@/components/clients/ClientActivityTimeline'
import { TimeSpentByDomain } from '@/components/clients/TimeSpentByDomain'
import { TimeSpentByCategory } from '@/components/clients/TimeSpentByCategory'
import { SummaryCard } from '@/components/dashboard/SummaryCard'
import { useClientActivity } from '@/hooks/useClients'
import { useClientSummary } from '@/hooks/useClientSummary'
import { useRangeSearchParams } from '@/lib/filters-store'
import { formatBytes, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'

const LIMIT = 50
const METHODS = ['GET', 'POST', 'HEAD', 'PUT', 'DELETE', 'CONNECT']
const ALL_METHODS = 'all'

export default function ClientDetailPage() {
  const { t } = useTranslation()
  const { clientIp } = useParams<{ clientIp: string }>()
  const [offset, setOffset] = useState(0)
  const [blockedOnly, setBlockedOnly] = useState(false)
  const [domainFilter, setDomainFilter] = useState('')
  const [method, setMethod] = useState(ALL_METHODS)
  const [timeSpentView, setTimeSpentView] = useState<'domain' | 'category'>('domain')

  const rangeParams = useRangeSearchParams()
  const summaryQuery = useClientSummary(clientIp, rangeParams)
  const query = useClientActivity({
    clientIp,
    rangeParams,
    limit: LIMIT,
    offset,
    blockedOnly,
    domain: domainFilter,
    method: method === ALL_METHODS ? undefined : method,
  })

  const summary = summaryQuery.data
  const isEmptyRange = summaryQuery.isSuccess && summary?.total_requests === 0

  function resetToFirstPage() {
    setOffset(0)
  }

  // A narrower range (or a new client) can leave `offset` pointing past the
  // new total -- e.g. paginated deep into a 7d view, then switching to a
  // tight custom range, would otherwise silently render "no activity" even
  // though matching events exist on page 1. Reset during render (React's
  // documented pattern for this) rather than an effect, to avoid an extra
  // cascading render.
  const pageResetKey = `${clientIp}|${JSON.stringify(rangeParams)}`
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
            <Link to="/clients" aria-label={t('clientDetail.back')}>
              <ArrowLeft className="h-4 w-4" />
            </Link>
          </Button>
          <h1 className="font-data text-lg font-semibold text-foreground">{clientIp}</h1>
        </div>
        <RangeSelector />
      </div>

      {isEmptyRange && (
        <div className="flex items-center gap-2 rounded-lg border border-border bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
          <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
          {t('common.noDataForRange')}
        </div>
      )}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <SummaryCard
          label={t('clientDetail.totalRequests')}
          value={summary?.total_requests ?? 0}
          icon={Activity}
          tone="info"
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
          tone="purple"
          loading={summaryQuery.isLoading}
          updating={summaryQuery.isFetching && !summaryQuery.isLoading}
          formatValue={formatBytes}
        />
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <Panel
          title={t('clientDetail.activityHistory')}
          className="xl:col-span-2"
          action={
            query.data && (
              <span
                className={cn(
                  'font-data text-xs text-muted-foreground transition-opacity duration-200',
                  query.isFetching && 'opacity-50',
                )}
              >
                {t('clientDetail.matchingEvents', { count: formatNumber(query.data.total) })}
              </span>
            )
          }
        >
          <div className="flex flex-wrap items-center gap-2 pb-1">
            <SearchFilterInput
              value={domainFilter}
              onChange={(value) => {
                setDomainFilter(value)
                resetToFirstPage()
              }}
              placeholder={t('clientDetail.filterByDomain')}
              ariaLabel={t('clientDetail.filterByDomain')}
              className="w-full sm:w-48"
            />
            <Select
              value={method}
              onValueChange={(value) => {
                setMethod(value)
                resetToFirstPage()
              }}
            >
              <SelectTrigger size="sm" className="w-28" aria-label={t('clientDetail.methodFilter')}>
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value={ALL_METHODS}>{t('clientDetail.allMethods')}</SelectItem>
                {METHODS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {option}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <Button
              variant={blockedOnly ? 'default' : 'outline'}
              size="sm"
              onClick={() => {
                setBlockedOnly((prev) => !prev)
                resetToFirstPage()
              }}
            >
              {t('common.blockedOnly')}
            </Button>
          </div>

          {query.isError ? (
            <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
          ) : (
            <>
              <ClientActivityTimeline events={query.data?.items ?? []} isLoading={query.isLoading} />
              {query.data && query.data.total > LIMIT && (
                <div className="flex items-center justify-between pt-3 text-xs text-muted-foreground">
                  <span className="font-data">
                    {t('common.rangeOf', {
                      start: offset + 1,
                      end: Math.min(offset + LIMIT, query.data.total),
                      total: query.data.total,
                    })}
                  </span>
                  <div className="flex gap-2">
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={offset === 0}
                      onClick={() => setOffset(Math.max(0, offset - LIMIT))}
                    >
                      {t('common.previous')}
                    </Button>
                    <Button
                      variant="outline"
                      size="sm"
                      disabled={offset + LIMIT >= query.data.total}
                      onClick={() => setOffset(offset + LIMIT)}
                    >
                      {t('common.next')}
                    </Button>
                  </div>
                </div>
              )}
            </>
          )}
        </Panel>

        <Panel
          title={t('clientDetail.timeSpent')}
          action={
            <div className="flex items-center gap-0.5 rounded-md border border-border bg-secondary/50 p-0.5">
              <button
                type="button"
                onClick={() => setTimeSpentView('domain')}
                aria-pressed={timeSpentView === 'domain'}
                className={cn(
                  'rounded-[calc(var(--radius-sm)-2px)] px-2 py-1 text-xs font-medium transition-colors duration-150',
                  timeSpentView === 'domain'
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t('clientDetail.byDomain')}
              </button>
              <button
                type="button"
                onClick={() => setTimeSpentView('category')}
                aria-pressed={timeSpentView === 'category'}
                className={cn(
                  'rounded-[calc(var(--radius-sm)-2px)] px-2 py-1 text-xs font-medium transition-colors duration-150',
                  timeSpentView === 'category'
                    ? 'bg-primary text-primary-foreground'
                    : 'text-muted-foreground hover:text-foreground',
                )}
              >
                {t('clientDetail.byCategory')}
              </button>
            </div>
          }
        >
          {timeSpentView === 'domain' ? (
            <TimeSpentByDomain clientIp={clientIp} rangeParams={rangeParams} />
          ) : (
            <TimeSpentByCategory clientIp={clientIp} rangeParams={rangeParams} />
          )}
        </Panel>
      </div>
    </div>
  )
}
