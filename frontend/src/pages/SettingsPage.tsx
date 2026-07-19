import { useState } from 'react'
import { toast } from 'sonner'
import { Download } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Panel } from '@/components/common/Panel'
import { UserManagementPanel } from '@/components/settings/UserManagementPanel'
import { AuditLogPanel } from '@/components/settings/AuditLogPanel'
import { DomainCategoriesPanel } from '@/components/settings/DomainCategoriesPanel'
import { AlertSettingsPanel } from '@/components/settings/AlertSettingsPanel'
import { ReportsPanel } from '@/components/settings/ReportsPanel'
import { downloadExport, ApiError } from '@/lib/api-client'
import { POLLING_FALLBACK_INTERVAL_MS } from '@/lib/constants'
import { useTranslation } from '@/i18n'
import type { RangeParam } from '@/types/api'

export default function SettingsPage() {
  const { t } = useTranslation()
  const [exportRange, setExportRange] = useState<RangeParam>('24h')
  const [exportFormat, setExportFormat] = useState<'csv' | 'json'>('csv')
  const [blockedOnly, setBlockedOnly] = useState(false)
  const [downloading, setDownloading] = useState(false)

  async function handleExport() {
    setDownloading(true)
    try {
      await downloadExport(exportRange, exportFormat, blockedOnly)
      toast.success(t('settings.exportSuccessToast'))
    } catch (err) {
      toast.error(err instanceof ApiError ? err.message : t('settings.exportErrorToast'))
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('settings.userManagement')}>
        <UserManagementPanel />
      </Panel>

      <Panel title={t('settings.auditLog')}>
        <AuditLogPanel />
      </Panel>

      <Panel title={t('settings.domainCategories')}>
        <DomainCategoriesPanel />
      </Panel>

      <Panel title={t('settings.alertSettings')}>
        <AlertSettingsPanel />
      </Panel>

      <Panel title={t('settings.reports')}>
        <ReportsPanel />
      </Panel>

      <Panel title={t('settings.liveUpdates')}>
        <dl className="grid grid-cols-1 gap-3 text-sm sm:grid-cols-2">
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              {t('settings.realtimeTransport')}
            </dt>
            <dd className="font-data mt-1 text-foreground">{t('settings.realtimeTransportValue')}</dd>
          </div>
          <div>
            <dt className="text-xs uppercase tracking-wide text-muted-foreground">
              {t('settings.pollingInterval')}
            </dt>
            <dd className="font-data mt-1 text-foreground">{POLLING_FALLBACK_INTERVAL_MS / 1000}s</dd>
          </div>
        </dl>
        <p className="text-xs text-muted-foreground">{t('settings.liveUpdatesDescription')}</p>
      </Panel>

      <Panel title={t('settings.exportEvents')}>
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <div className="flex flex-col gap-1.5">
              <Label>{t('settings.range')}</Label>
              <Select value={exportRange} onValueChange={(v) => setExportRange(v as RangeParam)}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="1h">{t('settings.rangeLastHour')}</SelectItem>
                  <SelectItem value="24h">{t('settings.rangeLast24Hours')}</SelectItem>
                  <SelectItem value="7d">{t('settings.rangeLast7Days')}</SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label>{t('settings.format')}</Label>
              <Select value={exportFormat} onValueChange={(v) => setExportFormat(v as 'csv' | 'json')}>
                <SelectTrigger>
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="csv">CSV</SelectItem>
                  <SelectItem value="json">JSON</SelectItem>
                </SelectContent>
              </Select>
            </div>
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

          <Button onClick={handleExport} disabled={downloading} className="w-fit gap-2">
            <Download className="h-4 w-4" aria-hidden="true" />
            {downloading ? t('settings.preparingExport') : t('settings.download')}
          </Button>
          <p className="text-xs text-muted-foreground">{t('settings.exportNote')}</p>
        </div>
      </Panel>
    </div>
  )
}
