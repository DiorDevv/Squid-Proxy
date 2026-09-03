import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { DataTable } from '@/components/common/DataTable'
import { formatBytes, formatNumber, formatRelativeTime } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { DomainClientStat } from '@/types/api'

interface DomainClientsTableProps {
  items: DomainClientStat[]
  total: number
  limit: number
  offset: number
  onOffsetChange: (offset: number) => void
  sorting: SortingState
  onSortingChange: (sorting: SortingState) => void
  isLoading: boolean
}

export function DomainClientsTable({
  items,
  total,
  limit,
  offset,
  onOffsetChange,
  sorting,
  onSortingChange,
  isLoading,
}: DomainClientsTableProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  const columns = useMemo<ColumnDef<DomainClientStat>[]>(
    () => [
      {
        accessorKey: 'client_ip',
        header: t('clients.columnClientIp'),
        cell: ({ getValue }) => <span className="font-data text-foreground">{getValue<string>()}</span>,
      },
      {
        accessorKey: 'branch',
        header: t('branch.filter'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{getValue<string | null>() ?? '—'}</span>
        ),
      },
      {
        accessorKey: 'user',
        header: t('clients.columnUser'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{getValue<string | null>() ?? '—'}</span>
        ),
      },
      {
        accessorKey: 'visit_count',
        header: t('domainDetail.columnVisits'),
        cell: ({ getValue }) => (
          <span className="font-data text-foreground">{formatNumber(getValue<number>())}</span>
        ),
      },
      {
        accessorKey: 'blocked_count',
        header: t('clients.columnBlocked'),
        cell: ({ getValue }) => {
          const value = getValue<number>()
          return (
            <span className={value > 0 ? 'font-data text-warning' : 'font-data text-muted-foreground'}>
              {formatNumber(value)}
            </span>
          )
        },
      },
      {
        accessorKey: 'total_bytes',
        header: t('clients.columnDataUsed'),
        cell: ({ getValue }) => (
          <span className="font-data text-foreground">{formatBytes(getValue<number>())}</span>
        ),
      },
      {
        accessorKey: 'last_visit',
        header: t('domainDetail.columnLastVisit'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{formatRelativeTime(getValue<string | null>())}</span>
        ),
      },
    ],
    [t],
  )

  return (
    <DataTable
      columns={columns}
      data={items}
      total={total}
      limit={limit}
      offset={offset}
      onOffsetChange={onOffsetChange}
      sorting={sorting}
      onSortingChange={(updater) => {
        const next = typeof updater === 'function' ? updater(sorting) : updater
        onSortingChange(next)
      }}
      manualSorting
      isLoading={isLoading}
      emptyMessage={t('domainDetail.noClients')}
      onRowClick={(row) => navigate(`/clients/${encodeURIComponent(row.client_ip)}`)}
    />
  )
}
