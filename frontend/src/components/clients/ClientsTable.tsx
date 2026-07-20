import { useMemo } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ColumnDef, SortingState } from '@tanstack/react-table'
import { DataTable } from '@/components/common/DataTable'
import { formatBytes, formatNumber, formatRelativeTime } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { ClientSummary } from '@/types/api'

interface ClientsTableProps {
  items: ClientSummary[]
  total: number
  limit: number
  offset: number
  onOffsetChange: (offset: number) => void
  sorting: SortingState
  onSortingChange: (sorting: SortingState) => void
  isLoading: boolean
}

export function ClientsTable({
  items,
  total,
  limit,
  offset,
  onOffsetChange,
  sorting,
  onSortingChange,
  isLoading,
}: ClientsTableProps) {
  const { t } = useTranslation()
  const navigate = useNavigate()

  // Only shown when the current page actually mixes branches -- with a
  // single branch (the common case) or an explicit branch filter applied,
  // every row would show the same value, which is noise, not information.
  const showBranchColumn = useMemo(() => new Set(items.map((item) => item.branch)).size > 1, [items])

  const columns = useMemo<ColumnDef<ClientSummary>[]>(
    () => [
      {
        accessorKey: 'client_ip',
        header: t('clients.columnClientIp'),
        cell: ({ getValue }) => <span className="font-data text-foreground">{getValue<string>()}</span>,
      },
      ...(showBranchColumn
        ? [
            {
              accessorKey: 'branch',
              header: t('branch.filter'),
              cell: ({ getValue }) => (
                <span className="font-data text-muted-foreground">{getValue<string | null>() ?? '—'}</span>
              ),
            } satisfies ColumnDef<ClientSummary>,
          ]
        : []),
      {
        accessorKey: 'user',
        header: t('clients.columnUser'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{getValue<string | null>() ?? '—'}</span>
        ),
      },
      {
        accessorKey: 'total_requests',
        header: t('clients.columnTotalRequests'),
        cell: ({ getValue }) => (
          <span className="font-data text-foreground">{formatNumber(getValue<number>())}</span>
        ),
      },
      {
        accessorKey: 'blocked_requests',
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
        accessorKey: 'last_activity',
        header: t('clients.columnLastActivity'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{formatRelativeTime(getValue<string | null>())}</span>
        ),
      },
    ],
    [t, showBranchColumn],
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
      emptyMessage={t('clients.empty')}
      onRowClick={(row) => navigate(`/clients/${encodeURIComponent(row.client_ip)}`)}
    />
  )
}
