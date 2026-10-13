import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { DataTable } from '@/components/common/DataTable'
import { formatDateTime, formatNumber } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { BlockedDomainRow } from '@/types/api'

interface BlockedDomainsTableProps {
  items: BlockedDomainRow[]
  total: number
  limit: number
  offset: number
  onOffsetChange: (offset: number) => void
  isLoading: boolean
  onRowClick?: (row: BlockedDomainRow) => void
  emptyMessage?: string
}

function LabelList({ values }: { values: string[] }) {
  const text = values.join(', ')
  return (
    <span className="font-data block max-w-[14rem] truncate text-muted-foreground" title={text || undefined}>
      {text || '—'}
    </span>
  )
}

export function BlockedDomainsTable({
  items,
  total,
  limit,
  offset,
  onOffsetChange,
  isLoading,
  onRowClick,
  emptyMessage,
}: BlockedDomainsTableProps) {
  const { t } = useTranslation()

  const columns = useMemo<ColumnDef<BlockedDomainRow>[]>(
    () => [
      {
        accessorKey: 'domain',
        header: t('blocked.columnDomain'),
        cell: ({ getValue }) => (
          <span className="font-data block max-w-[24rem] truncate text-foreground" title={getValue<string>()}>
            {getValue<string>()}
          </span>
        ),
      },
      {
        accessorKey: 'denied_count',
        header: t('blocked.domains.columnDenied'),
        cell: ({ getValue }) => (
          <span className="font-data text-warning">{formatNumber(getValue<number>())}</span>
        ),
      },
      {
        accessorKey: 'auth_count',
        header: t('blocked.domains.columnAuth'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{formatNumber(getValue<number>())}</span>
        ),
      },
      {
        accessorKey: 'client_count',
        header: t('blocked.domains.columnClients'),
        cell: ({ getValue }) => <span className="font-data text-foreground">{formatNumber(getValue<number>())}</span>,
      },
      {
        accessorKey: 'branches',
        header: t('branch.filter'),
        cell: ({ getValue }) => <LabelList values={getValue<string[]>()} />,
      },
      {
        accessorKey: 'proxies',
        header: t('blocked.domains.columnProxies'),
        cell: ({ getValue }) => <LabelList values={getValue<string[]>()} />,
      },
      {
        accessorKey: 'last_seen',
        header: t('blocked.domains.columnLastSeen'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{formatDateTime(getValue<string>())}</span>
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
      isLoading={isLoading}
      onRowClick={onRowClick}
      emptyMessage={emptyMessage ?? t('blocked.domains.empty')}
    />
  )
}
