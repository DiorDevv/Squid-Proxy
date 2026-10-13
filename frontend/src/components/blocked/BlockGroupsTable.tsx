import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { DataTable } from '@/components/common/DataTable'
import { formatDateTime, formatNumber } from '@/lib/format'
import { GROUP_LABELS, groupKeyLabel } from '@/lib/block-filters'
import { useTranslation } from '@/i18n'
import type { BlockGroupBy, BlockGroupRow } from '@/types/api'

interface BlockGroupsTableProps {
  group: BlockGroupBy
  items: BlockGroupRow[]
  total: number
  limit: number
  offset: number
  onOffsetChange: (offset: number) => void
  isLoading: boolean
  onRowClick?: (row: BlockGroupRow) => void
  emptyMessage?: string
}

function LabelList({ values }: { values: string[] }) {
  const text = values.join(', ')
  return (
    <span className="font-data block max-w-[12rem] truncate text-muted-foreground" title={text || undefined}>
      {text || '—'}
    </span>
  )
}

const count = (className: string) =>
  function CountCell({ getValue }: { getValue: () => unknown }) {
    return <span className={`font-data ${className}`}>{formatNumber(getValue() as number)}</span>
  }

export function BlockGroupsTable({
  group,
  items,
  total,
  limit,
  offset,
  onOffsetChange,
  isLoading,
  onRowClick,
  emptyMessage,
}: BlockGroupsTableProps) {
  const { t } = useTranslation()

  const columns = useMemo<ColumnDef<BlockGroupRow>[]>(() => {
    const cols: (ColumnDef<BlockGroupRow> | false)[] = [
      {
        accessorKey: 'key',
        header: t(GROUP_LABELS[group]),
        cell: ({ getValue }) => {
          const key = getValue<string>()
          return (
            <span
              className={`font-data block max-w-[22rem] truncate ${key ? 'text-foreground' : 'italic text-muted-foreground'}`}
              title={key || undefined}
            >
              {groupKeyLabel(t, group, key)}
            </span>
          )
        },
      },
      { accessorKey: 'denied_count', header: t('blocked.summary.denied'), cell: count('text-warning') },
      { accessorKey: 'auth_count', header: t('blocked.summary.auth'), cell: count('text-muted-foreground') },
      group !== 'client' && {
        accessorKey: 'client_count',
        header: t('blocked.summary.clients'),
        cell: count('text-foreground'),
      },
      group !== 'user' && { accessorKey: 'user_count', header: t('blocked.summary.users'), cell: count('text-foreground') },
      group !== 'domain' && {
        accessorKey: 'domain_count',
        header: t('blocked.summary.domains'),
        cell: count('text-foreground'),
      },
      group !== 'branch' && {
        accessorKey: 'branches',
        header: t('branch.filter'),
        cell: ({ getValue }) => <LabelList values={getValue<string[]>()} />,
      },
      group !== 'proxy' && {
        accessorKey: 'proxies',
        header: t('blocked.group.proxy'),
        cell: ({ getValue }) => <LabelList values={getValue<string[]>()} />,
      },
      {
        accessorKey: 'last_seen',
        header: t('blocked.analysis.lastSeen'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{formatDateTime(getValue<string>())}</span>
        ),
      },
    ]
    return cols.filter((c): c is ColumnDef<BlockGroupRow> => c !== false)
  }, [t, group])

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
      emptyMessage={emptyMessage ?? t('blocked.analysis.empty')}
    />
  )
}
