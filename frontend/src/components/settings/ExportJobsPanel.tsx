import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import type { ColumnDef } from '@tanstack/react-table'
import { Share2, Copy, X } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Tooltip, TooltipContent, TooltipTrigger } from '@/components/ui/tooltip'
import { DataTable } from '@/components/common/DataTable'
import { ApiError } from '@/lib/api-client'
import { formatBytes, formatDateTime, formatNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useExportJobs, useCreateExportShareLink, useRevokeExportShareLink } from '@/hooks/useExportJob'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { ExportJob, ExportJobStatus, ExportShareLink } from '@/types/api'

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

function copyToClipboard(t: (key: TranslationKey) => string, value: string) {
  navigator.clipboard.writeText(value)
  toast.success(t('settings.copiedToast'))
}

function ChecksumCell({ checksum }: { checksum: string | null }) {
  const { t } = useTranslation()
  if (!checksum) return <span className="text-muted-foreground">—</span>
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={() => copyToClipboard(t, checksum)}
          className="font-data text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          {checksum.slice(0, 10)}…
        </button>
      </TooltipTrigger>
      <TooltipContent>{checksum}</TooltipContent>
    </Tooltip>
  )
}

/** A finished job's share-link management, in a small dialog rather than
 * inline in the table -- generating one shows the raw token exactly once
 * (see export_job_service.create_share_link's docstring on why ExportJobOut
 * itself never carries it), so this needs somewhere to hold that value only
 * for the current dialog session, then discard it. */
function ShareCell({ job }: { job: ExportJob }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [freshLink, setFreshLink] = useState<ExportShareLink | null>(null)
  const createLink = useCreateExportShareLink()
  const revokeLink = useRevokeExportShareLink()

  if (job.status !== 'done') return <span className="text-muted-foreground">—</span>

  function handleOpenChange(next: boolean) {
    setOpen(next)
    if (!next) setFreshLink(null)
  }

  function handleGenerate() {
    createLink.mutate(job.id, {
      onSuccess: setFreshLink,
      onError: (err) => toast.error(err instanceof ApiError ? err.message : t('settings.shareLinkErrorToast')),
    })
  }

  function handleRevoke() {
    revokeLink.mutate(job.id, {
      onSuccess: () => {
        setFreshLink(null)
        toast(t('settings.shareLinkRevokedToast'))
      },
      onError: (err) => toast.error(err instanceof ApiError ? err.message : t('settings.shareLinkErrorToast')),
    })
  }

  const fullUrl = freshLink ? `${window.location.origin}${freshLink.download_url}` : null

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogTrigger asChild>
        <Button variant="ghost" size="icon-sm" aria-label={t('settings.shareExport')}>
          <Share2 className={cn('h-4 w-4', job.share_link_active && 'text-info')} aria-hidden="true" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{t('settings.shareExportDialogTitle')}</DialogTitle>
          <DialogDescription>{t('settings.shareExportDialogDescription')}</DialogDescription>
        </DialogHeader>

        {freshLink && fullUrl ? (
          <div className="flex flex-col gap-2">
            <p className="text-xs text-muted-foreground">{t('settings.shareLinkShownOnce')}</p>
            <div className="flex items-center gap-2">
              <code className="font-data flex-1 truncate rounded-md bg-muted px-2 py-1.5 text-xs">{fullUrl}</code>
              <Button variant="outline" size="icon-sm" onClick={() => copyToClipboard(t, fullUrl)}>
                <Copy className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
            <p className="text-xs text-muted-foreground">
              {t('settings.shareLinkExpiresAt', { date: formatDateTime(freshLink.expires_at) })}
            </p>
          </div>
        ) : job.share_link_active ? (
          <div className="flex flex-col gap-3">
            <p className="text-xs text-muted-foreground">
              {t('settings.shareLinkActiveDescription', {
                date: job.share_link_expires_at ? formatDateTime(job.share_link_expires_at) : '',
              })}
            </p>
            <Button
              variant="outline"
              onClick={handleRevoke}
              disabled={revokeLink.isPending}
              className="w-fit gap-2"
            >
              <X className="h-4 w-4" aria-hidden="true" />
              {t('settings.shareLinkRevoke')}
            </Button>
          </div>
        ) : (
          <Button onClick={handleGenerate} disabled={createLink.isPending} className="w-fit gap-2">
            <Share2 className="h-4 w-4" aria-hidden="true" />
            {t('settings.shareLinkGenerate')}
          </Button>
        )}
      </DialogContent>
    </Dialog>
  )
}

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
        id: 'filters',
        header: t('settings.exportColumnFilters'),
        cell: ({ row }) => {
          const job = row.original
          const parts = [
            job.domain && `domain~${job.domain}`,
            job.client_ip && `ip=${job.client_ip}`,
            job.category && job.category,
            job.columns && `${job.columns.length} cols`,
          ].filter(Boolean)
          return parts.length > 0 ? (
            <span className="font-data text-xs text-muted-foreground">{parts.join(', ')}</span>
          ) : (
            <span className="text-muted-foreground">—</span>
          )
        },
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
        accessorKey: 'checksum_sha256',
        header: t('settings.exportColumnChecksum'),
        cell: ({ getValue }) => <ChecksumCell checksum={getValue<string | null>()} />,
      },
      {
        accessorKey: 'created_at',
        header: t('settings.exportColumnCreated'),
        cell: ({ getValue }) => (
          <span className="font-data text-xs text-muted-foreground">{formatDateTime(getValue<string>())}</span>
        ),
      },
      {
        id: 'share',
        header: t('settings.exportColumnShare'),
        cell: ({ row }) => <ShareCell job={row.original} />,
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
