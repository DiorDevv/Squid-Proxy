import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { DataTable } from '@/components/common/DataTable'
import { StatusBadge } from '@/components/common/StatusBadge'
import { formatDateTime } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { LiveEvent } from '@/types/events'

interface BlockedEventsTableProps {
  items: LiveEvent[]
  isLoading: boolean
  emptyMessage?: string
}

export function BlockedEventsTable({ items, isLoading, emptyMessage }: BlockedEventsTableProps) {
  const { t } = useTranslation()

  const columns = useMemo<ColumnDef<LiveEvent>[]>(
    () => [
      {
        accessorKey: 'timestamp',
        header: t('blocked.columnTime'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{formatDateTime(getValue<string>())}</span>
        ),
      },
      {
        accessorKey: 'client_ip',
        header: t('blocked.columnClientIp'),
        cell: ({ getValue }) => <span className="font-data text-foreground">{getValue<string>()}</span>,
      },
      {
        accessorKey: 'user',
        header: t('blocked.columnUser'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{getValue<string | null>() ?? '—'}</span>
        ),
      },
      {
        id: 'target',
        header: t('blocked.columnDomain'),
        cell: ({ row }) => (
          <span className="font-data text-foreground" title={row.original.url}>
            {row.original.domain ?? row.original.url}
          </span>
        ),
      },
      {
        accessorKey: 'status_code',
        header: t('blocked.columnStatus'),
        cell: ({ getValue }) => <span className="font-data text-warning">{getValue<number>()}</span>,
      },
      {
        id: 'status',
        header: t('blocked.columnOutcome'),
        cell: () => <StatusBadge blocked />,
      },
    ],
    [t],
  )

  return (
    <DataTable
      columns={columns}
      data={items}
      total={items.length}
      limit={Math.max(items.length, 1)}
      offset={0}
      onOffsetChange={() => {}}
      isLoading={isLoading}
      emptyMessage={emptyMessage ?? t('blocked.emptyDefault')}
    />
  )
}
