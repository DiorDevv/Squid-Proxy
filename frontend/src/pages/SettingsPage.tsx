import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Download, X, ChevronDown } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import { Input } from '@/components/ui/input'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { UserManagementPanel } from '@/components/settings/UserManagementPanel'
import { AuditLogPanel } from '@/components/settings/AuditLogPanel'
import { DomainCategoriesPanel } from '@/components/settings/DomainCategoriesPanel'
import { AlertSettingsPanel } from '@/components/settings/AlertSettingsPanel'
import { ReportsPanel } from '@/components/settings/ReportsPanel'
import { ExportJobsPanel } from '@/components/settings/ExportJobsPanel'
import { ExportSettingsPanel } from '@/components/settings/ExportSettingsPanel'
import { downloadExportJob, ApiError } from '@/lib/api-client'
import { useCancelExportJob, useCreateExportJob, useExportJob } from '@/hooks/useExportJob'
import { useBranches } from '@/hooks/useBranches'
import { useFiltersStore } from '@/lib/filters-store'
import { formatNumber, toDatetimeLocalValue } from '@/lib/format'
import { EXPORT_COLUMNS, POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import { CATEGORY_LABEL_KEYS, CATEGORY_OPTIONS } from '@/lib/categories'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { DomainCategoryLabel, RangeParam } from '@/types/api'

const TERMINAL_STATUSES = new Set(['done', 'failed', 'cancelled'])
const ALL_BRANCHES = 'all'
const ALL_CATEGORIES = 'all'
const CUSTOM_RANGE = 'custom'
type ExportRangeValue = RangeParam | typeof CUSTOM_RANGE
type ExportFormatValue = 'csv' | 'json' | 'xlsx'

// Matches app/services/export_service.py's EXPORT_COLUMNS' own labels --
// short, technical column names rather than full sentences, since this is
// a picker for a CSV/JSON/XLSX field list, not prose.
const EXPORT_COLUMN_LABEL_KEYS: Record<(typeof EXPORT_COLUMNS)[number], TranslationKey> = {
  id: 'settings.exportColumnId',
  timestamp: 'settings.exportColumnTimestamp',
  client_ip: 'settings.exportColumnClientIp',
  branch: 'settings.exportColumnBranch',
  user: 'settings.exportColumnUser',
  method: 'settings.exportColumnMethod',
  url: 'settings.exportColumnUrl',
  domain: 'settings.exportColumnDomain',
  action: 'settings.exportColumnAction',
  status_code: 'settings.exportColumnStatusCode',
  bytes: 'settings.exportColumnBytes',
  blocked: 'settings.exportColumnBlocked',
}

export default function SettingsPage() {
  const { t } = useTranslation()
  // Initialized from (not bound to) the same global range/branch filter the
  // Dashboard/Domains/Clients/Blocked pages all share (useFiltersStore) --
  // otherwise this defaulted to a flat 24h regardless of what the admin was
  // just looking at elsewhere, so "export this" after picking e.g. 1h on
  // the Dashboard silently exported 24h of data instead. A one-time read
  // via getState() (not the reactive useFiltersStore() hook) so editing
  // these fields here never feeds back and changes what other pages show.
  const initialFilters = useFiltersStore.getState()
  const [exportRange, setExportRange] = useState<ExportRangeValue>(
    initialFilters.mode === 'custom' ? CUSTOM_RANGE : initialFilters.range,
  )
  const [customFrom, setCustomFrom] = useState(() =>
    initialFilters.mode === 'custom' && initialFilters.customFrom
      ? toDatetimeLocalValue(new Date(initialFilters.customFrom))
      : toDatetimeLocalValue(new Date(Date.now() - 24 * 60 * 60 * 1000)),
  )
  const [customTo, setCustomTo] = useState(() =>
    initialFilters.mode === 'custom' && initialFilters.customTo
      ? toDatetimeLocalValue(new Date(initialFilters.customTo))
      : toDatetimeLocalValue(new Date()),
  )
  const [exportFormat, setExportFormat] = useState<ExportFormatValue>('csv')
  const [exportBranch, setExportBranch] = useState<string | null>(initialFilters.branch)
  const [blockedOnly, setBlockedOnly] = useState(false)
  // Narrower filters than range/branch/blockedOnly above -- all optional,
  // all forwarded straight through to GET /api/export/jobs (see
  // event_query_service.build_event_conditions server-side for the same
  // domain=substring vs category=exact-set distinction these two encode).
  const [exportClientIp, setExportClientIp] = useState('')
  const [exportDomain, setExportDomain] = useState('')
  const [exportCategory, setExportCategory] = useState<DomainCategoryLabel | null>(null)
  // null means "every column" (the picker's own default) -- matches the
  // backend's own None-means-all convention (see resolve_columns), so an
  // admin who never opens the picker gets exactly the pre-existing behavior.
  const [exportColumns, setExportColumns] = useState<string[] | null>(null)
  const [jobId, setJobId] = useState<string | null>(null)

  const branches = useBranches()

  const createJob = useCreateExportJob()
  const cancelJob = useCancelExportJob()
  const job = useExportJob(jobId)
  // Re-enables the button as soon as the job leaves pending/running (or the
  // status poll itself gives up, e.g. a network blip -- see the effect
  // below) -- for 'done' that's a beat before the download actually
  // finishes, for 'failed'/'cancelled' there's nothing further to wait for.
  const active = jobId !== null && !job.isError && !TERMINAL_STATUSES.has(job.data?.status ?? '')

  // Runs the job through to completion once it lands on a terminal status --
  // POST /export/jobs only hands back the initial PENDING row, so the
  // actual file download and success/error/cancelled toast happen here,
  // driven by useExportJob's polling (see hooks/useExportJob.ts).
  useEffect(() => {
    if (jobId === null) return
    if (job.isError) {
      // useExportJob's refetchInterval only fires while it has a known
      // pending/running status; once the poll itself starts erroring
      // (dropped connection, 5xx, ...) it never gets that status again and
      // would otherwise stop polling forever with the button stuck
      // disabled -- surface it and let the user just start a new export.
      toast.error(
        job.error instanceof ApiError ? job.error.message : t('settings.exportErrorToast'),
      )
      return
    }
    if (!job.data) return
    if (job.data.status === 'done') {
      const downloadingJobId = jobId
      downloadExportJob(downloadingJobId)
        .then(() => toast.success(t('settings.exportSuccessToast')))
        .catch((err) =>
          toast.error(err instanceof ApiError ? err.message : t('settings.exportErrorToast')),
        )
        .finally(() =>
          // Only clear the tracker if it's still pointing at *this*
          // download -- if the admin already started a second export while
          // this one's blob fetch was still in flight, jobId has moved on
          // to the new job's id, and clobbering it here would silently
          // stop the UI from tracking/auto-downloading that second export.
          setJobId((current) => (current === downloadingJobId ? null : current)),
        )
    } else if (job.data.status === 'failed') {
      toast.error(job.data.error_message || t('settings.exportErrorToast'))
    } else if (job.data.status === 'cancelled') {
      toast(t('settings.exportCancelledToast'))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job.data?.status, job.isError])

  function handleExport() {
    const extraFilters = {
      clientIp: exportClientIp.trim() || null,
      domain: exportDomain.trim() || null,
      category: exportCategory,
      columns: exportColumns,
    }
    let params: Parameters<typeof createJob.mutate>[0]
    if (exportRange === CUSTOM_RANGE) {
      const from = new Date(customFrom)
      const to = new Date(customTo)
      if (!customFrom || !customTo || Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
        toast.error(t('common.rangeIncomplete'))
        return
      }
      if (from >= to) {
        toast.error(t('common.rangeInvalidOrder'))
        return
      }
      params = {
        fromTs: from.toISOString(),
        toTs: to.toISOString(),
        format: exportFormat,
        blockedOnly,
        branch: exportBranch,
        ...extraFilters,
      }
    } else {
      params = {
        range: exportRange,
        format: exportFormat,
        blockedOnly,
        branch: exportBranch,
        ...extraFilters,
      }
    }

    createJob.mutate(params, {
      onSuccess: (created) => setJobId(created.id),
      onError: (err) =>
        toast.error(err instanceof ApiError ? err.message : t('settings.exportErrorToast')),
    })
  }

  function toggleExportColumn(column: string, checked: boolean) {
    setExportColumns((current) => {
      // First checkbox flip after "all columns" starts from the full list
      // (not just the one being unchecked) -- unchecking "url" from "every
      // column selected" should leave every *other* column still selected,
      // not just id/url as if only two had ever been picked.
      const base = current ?? [...EXPORT_COLUMNS]
      const next = checked ? [...new Set([...base, column])] : base.filter((c) => c !== column)
      // Re-collapse back to "all" (null) once every column is checked again
      // -- keeps the picker's own displayed state consistent with what a
      // fresh page load would show, and avoids sending a full, spelled-out
      // column list to the API when "no filter at all" means the same thing.
      return next.length === EXPORT_COLUMNS.length ? null : next
    })
  }

  function handleCancel() {
    if (jobId === null) return
    cancelJob.mutate(jobId, {
      onError: (err) =>
        toast.error(err instanceof ApiError ? err.message : t('settings.exportCancelErrorToast')),
    })
  }

  // row_count updates live while the job is RUNNING (see
  // export_job_service.run_job), so a wide range that takes minutes shows
  // real progress instead of a silent "preparing" with nothing to go on.
  function exportButtonLabel(): string {
    if (!active && !createJob.isPending) return t('settings.download')
    const rowCount = job.data?.row_count
    return rowCount != null
      ? t('settings.preparingExportWithCount', { count: formatNumber(rowCount) })
      : t('settings.preparingExport')
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('settings.userManagement')}>
        <PanelErrorBoundary panelLabel={t('settings.userManagement')}>
          <UserManagementPanel />
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('settings.auditLog')}>
        <PanelErrorBoundary panelLabel={t('settings.auditLog')}>
          <AuditLogPanel />
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('settings.domainCategories')}>
        <PanelErrorBoundary panelLabel={t('settings.domainCategories')}>
          <DomainCategoriesPanel />
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('settings.alertSettings')}>
        <PanelErrorBoundary panelLabel={t('settings.alertSettings')}>
          <AlertSettingsPanel />
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('settings.reports')}>
        <PanelErrorBoundary panelLabel={t('settings.reports')}>
          <ReportsPanel />
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('settings.liveUpdates')}>
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              {t('settings.realtimeTransport')}
            </dt>
            <dd className="font-data mt-1 text-foreground">
              {t('settings.realtimeTransportValue')}
            </dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              {t('settings.pollingInterval')}
            </dt>
            <dd className="font-data mt-1 text-foreground">
              {POLLING_FALLBACK_INTERVAL_MS / 1000}s
            </dd>
          </div>
        </dl>
        <p className="text-xs text-muted-foreground">{t('settings.liveUpdatesDescription')}</p>
      </Panel>

      <Panel title={t('settings.exportEvents')}>
        <PanelErrorBoundary panelLabel={t('settings.exportEvents')}>
          <div className="flex flex-col gap-4">
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
              <div className="flex flex-col gap-1.5">
                <Label>{t('settings.range')}</Label>
                <Select
                  value={exportRange}
                  onValueChange={(v) => setExportRange(v as ExportRangeValue)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1h">{t('settings.rangeLastHour')}</SelectItem>
                    <SelectItem value="24h">{t('settings.rangeLast24Hours')}</SelectItem>
                    <SelectItem value="7d">{t('settings.rangeLast7Days')}</SelectItem>
                    <SelectItem value={CUSTOM_RANGE}>{t('common.custom')}</SelectItem>
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">
                  {t('settings.exportRangeIndependent')}
                </p>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>{t('settings.format')}</Label>
                <Select
                  value={exportFormat}
                  onValueChange={(v) => setExportFormat(v as ExportFormatValue)}
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="csv">CSV</SelectItem>
                    <SelectItem value="json">JSON</SelectItem>
                    <SelectItem value="xlsx">Excel (.xlsx)</SelectItem>
                  </SelectContent>
                </Select>
              </div>
              {/* Single-branch deployments (the common case) have nothing to
                filter by -- same threshold BranchSelector.tsx uses. */}
              {(branches.data?.items.length ?? 0) > 1 && (
                <div className="flex flex-col gap-1.5">
                  <Label>{t('branch.filter')}</Label>
                  <Select
                    value={exportBranch ?? ALL_BRANCHES}
                    onValueChange={(v) => setExportBranch(v === ALL_BRANCHES ? null : v)}
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value={ALL_BRANCHES}>{t('branch.all')}</SelectItem>
                      {branches.data?.items.map((item) => (
                        <SelectItem key={item.slug} value={item.slug}>
                          {item.label}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
              <div className="flex items-end gap-2 pb-1.5">
                <Checkbox
                  id="blocked-only-export"
                  checked={blockedOnly}
                  onCheckedChange={(checked) => setBlockedOnly(checked === true)}
                />
                <Label htmlFor="blocked-only-export" className="font-normal">
                  {t('common.blockedOnly')}
                </Label>
              </div>
            </div>

            {/* Narrower filters than range/branch/blocked-only above -- kept
              in their own row since they're used less often, rather than
              crowding the primary controls. */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-4">
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="export-domain">{t('settings.exportDomainFilter')}</Label>
                <Input
                  id="export-domain"
                  placeholder={t('settings.exportDomainFilterPlaceholder')}
                  value={exportDomain}
                  onChange={(e) => setExportDomain(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="export-client-ip">{t('settings.exportClientIpFilter')}</Label>
                <Input
                  id="export-client-ip"
                  placeholder="10.0.0.5"
                  value={exportClientIp}
                  onChange={(e) => setExportClientIp(e.target.value)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>{t('domains.categoryFilter')}</Label>
                <Select
                  value={exportCategory ?? ALL_CATEGORIES}
                  onValueChange={(v) =>
                    setExportCategory(v === ALL_CATEGORIES ? null : (v as DomainCategoryLabel))
                  }
                >
                  <SelectTrigger>
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value={ALL_CATEGORIES}>{t('domains.allCategories')}</SelectItem>
                    {CATEGORY_OPTIONS.map((option) => (
                      <SelectItem key={option} value={option}>
                        {t(CATEGORY_LABEL_KEYS[option])}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label>{t('settings.exportColumns')}</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" className="justify-between font-normal">
                      {exportColumns === null
                        ? t('settings.exportAllColumns')
                        : t('settings.exportColumnsSelected', { count: exportColumns.length })}
                      <ChevronDown className="h-4 w-4 opacity-60" aria-hidden="true" />
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent align="start" className="flex w-56 flex-col gap-2">
                    {EXPORT_COLUMNS.map((column) => {
                      const checked = exportColumns === null || exportColumns.includes(column)
                      return (
                        <div key={column} className="flex items-center gap-2">
                          <Checkbox
                            id={`export-column-${column}`}
                            checked={checked}
                            onCheckedChange={(v) => toggleExportColumn(column, v === true)}
                          />
                          <Label htmlFor={`export-column-${column}`} className="font-normal">
                            {t(EXPORT_COLUMN_LABEL_KEYS[column])}
                          </Label>
                        </div>
                      )
                    })}
                  </PopoverContent>
                </Popover>
              </div>
            </div>

            {exportRange === CUSTOM_RANGE && (
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="export-range-from">{t('common.from')}</Label>
                  <input
                    id="export-range-from"
                    type="datetime-local"
                    value={customFrom}
                    onChange={(e) => setCustomFrom(e.target.value)}
                    className="font-data h-9 rounded-md border border-input bg-background px-2 text-xs text-foreground transition-all duration-150 outline-none hover:border-ring/40 focus-visible:border-ring focus-visible:shadow-[0_0_16px_-6px_var(--ring)]"
                  />
                </div>
                <div className="flex flex-col gap-1.5">
                  <Label htmlFor="export-range-to">{t('common.to')}</Label>
                  <input
                    id="export-range-to"
                    type="datetime-local"
                    value={customTo}
                    onChange={(e) => setCustomTo(e.target.value)}
                    className="font-data h-9 rounded-md border border-input bg-background px-2 text-xs text-foreground transition-all duration-150 outline-none hover:border-ring/40 focus-visible:border-ring focus-visible:shadow-[0_0_16px_-6px_var(--ring)]"
                  />
                </div>
              </div>
            )}

            <div className="flex items-center gap-2">
              <Button
                onClick={handleExport}
                disabled={active || createJob.isPending}
                className="w-fit gap-2"
              >
                <Download className="h-4 w-4" aria-hidden="true" />
                {exportButtonLabel()}
              </Button>
              {active && (
                <Button
                  onClick={handleCancel}
                  disabled={cancelJob.isPending}
                  variant="outline"
                  className="w-fit gap-2"
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                  {t('settings.cancelExport')}
                </Button>
              )}
            </div>
            <p className="text-xs text-muted-foreground">{t('settings.exportNote')}</p>
          </div>
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('settings.recentExports')}>
        <PanelErrorBoundary panelLabel={t('settings.recentExports')}>
          <ExportJobsPanel />
        </PanelErrorBoundary>
      </Panel>

      <Panel title={t('settings.exportCleanupSettings')}>
        <PanelErrorBoundary panelLabel={t('settings.exportCleanupSettings')}>
          <ExportSettingsPanel />
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
