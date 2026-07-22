import { useMemo } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { Badge } from '@/components/ui/badge'
import { DataTable } from '@/components/common/DataTable'
import { formatBytes, formatDateTime, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useExportJobs } from '@/hooks/useExportJob'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { ExportJob, ExportJobStatus } from '@/types/api'

const STATUS_LABEL_KEYS: Record<ExportJobStatus, TranslationKey> = {
  pending: 'settings.exportStatusPending',
  running: 'settings.exportStatusRunning',
  done: 'settings.exportStatusDone',
  failed: 'settings.exportStatusFailed',
  cancelled: 'settings.exportStatusCancelled',
}

// Matches the bg-x/15 text-x pattern used by StatusBadge.tsx and other
// status pills elsewhere in the app, rather than Badge's own built-in
// variants (which don't have a distinct "in progress" look).
const STATUS_CLASSES: Record<ExportJobStatus, string> = {
  pending: 'bg-muted text-muted-foreground',
  running: 'bg-info/15 text-info',
  done: 'bg-success/15 text-success',
  failed: 'bg-destructive/15 text-destructive',
  cancelled: 'bg-muted text-muted-foreground',
}

const RECENT_JOBS_LIMIT = 20

/** Shows every export job (not just whichever one the current browser tab
 * happens to be tracking, see hooks/useExportJob's useExportJob) so an
 * admin can see what's running, what finished, how many rows, and why
 * something failed -- GET /api/export/jobs already returns this, it just
 * had no UI before. */
export function ExportJobsPanel() {
  const { t } = useTranslation()
  const jobs = useExportJobs()

  const columns = useMemo<ColumnDef<ExportJob, unknown>[]>(
    () => [
      {
        accessorKey: 'status',
        header: t('settings.exportColumnStatus'),
        cell: ({ getValue }) => {
          const status = getValue<ExportJobStatus>()
          return (
            <Badge className={cn('border-transparent', STATUS_CLASSES[status])}>
              {t(STATUS_LABEL_KEYS[status])}
            </Badge>
          )
        },
      },
      {
        accessorKey: 'format',
        header: t('settings.exportColumnFormat'),
        cell: ({ getValue }) => (
          <span className="font-data uppercase text-foreground">{getValue<string>()}</span>
        ),
      },
      {
        id: 'range',
        header: t('settings.exportColumnRange'),
        cell: ({ row }) => (
          <span className="font-data text-xs text-muted-foreground">
            {formatDateTime(row.original.since)} → {formatDateTime(row.original.until)}
            {row.original.branch && ` (${row.original.branch})`}
          </span>
        ),
      },
      {
        accessorKey: 'row_count',
        header: t('settings.exportColumnRows'),
        cell: ({ getValue }) => {
          const rowCount = getValue<number | null>()
          return <span className="font-data text-foreground">{rowCount === null ? '—' : formatNumber(rowCount)}</span>
        },
      },
      {
        accessorKey: 'file_size_bytes',
        header: t('settings.exportColumnSize'),
        cell: ({ getValue }) => {
          const bytes = getValue<number | null>()
          return <span className="font-data text-foreground">{bytes === null ? '—' : formatBytes(bytes)}</span>
        },
      },
      {
        accessorKey: 'created_at',
        header: t('settings.exportColumnCreated'),
        cell: ({ getValue }) => (
          <span className="font-data text-xs text-muted-foreground">{formatDateTime(getValue<string>())}</span>
        ),
      },
    ],
    [t],
  )

  const data = jobs.data ?? []

  return (
    <DataTable
      columns={columns}
      data={data}
      total={data.length}
      limit={RECENT_JOBS_LIMIT}
      offset={0}
      onOffsetChange={() => {}}
      isLoading={jobs.isLoading}
      emptyMessage={t('settings.recentExportsEmpty')}
    />
  )
}
