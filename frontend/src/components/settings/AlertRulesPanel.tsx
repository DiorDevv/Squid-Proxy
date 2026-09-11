import { useState } from 'react'
import { toast } from 'sonner'
import { Pencil, Plus, Trash2 } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/common/ErrorState'
import {
  useAlertRules,
  useCreateAlertRule,
  useDeleteAlertRule,
  useUpdateAlertRule,
} from '@/hooks/useAlertSettings'
import { formatBytes, formatNumber } from '@/lib/format'
import { SCOPE_LABEL_KEYS, METRIC_LABEL_KEYS, isByteMetric } from '@/lib/alertRules'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { AlertRuleInput, AlertRuleMetric, AlertRuleOut, AlertRuleScope, AnomalySeverity } from '@/types/api'

const SCOPE_OPTIONS: AlertRuleScope[] = ['client_ip', 'domain', 'branch']
const METRIC_OPTIONS: AlertRuleMetric[] = ['request_count', 'blocked_count', 'total_bytes', 'bytes_received']
const SEVERITY_OPTIONS: AnomalySeverity[] = ['low', 'medium', 'high', 'critical']

const SEVERITY_LABEL_KEYS: Record<AnomalySeverity, TranslationKey> = {
  low: 'insights.severityLow',
  medium: 'insights.severityMedium',
  high: 'insights.severityHigh',
  critical: 'insights.severityCritical',
}

const SEVERITY_BADGE_VARIANT: Record<AnomalySeverity, 'secondary' | 'default' | 'destructive'> = {
  low: 'secondary',
  medium: 'secondary',
  high: 'default',
  critical: 'destructive',
}

function formatThreshold(metric: AlertRuleMetric, value: number): string {
  return isByteMetric(metric) ? formatBytes(value) : formatNumber(value)
}

/** Admin-defined custom threshold rules (Settings -> Alerts -> Custom
 * rules) -- the generic escape hatch so a new "flag X when Y crosses Z in
 * N minutes" check doesn't need a code change, only a row here. Evaluated
 * every aggregator flush by the backend (app/insights/anomaly.py). */
export function AlertRulesPanel({ branch }: { branch: string }) {
  const { t } = useTranslation()
  const query = useAlertRules(branch)
  const createRule = useCreateAlertRule(branch)
  const updateRule = useUpdateAlertRule(branch)
  const deleteRule = useDeleteAlertRule(branch)

  const [editing, setEditing] = useState<AlertRuleOut | 'new' | null>(null)
  const [pendingDelete, setPendingDelete] = useState<AlertRuleOut | null>(null)

  function handleSave(body: AlertRuleInput) {
    if (editing === 'new' || editing === null) {
      createRule.mutate(body, {
        onSuccess: () => {
          toast.success(t('settings.alertRules.saved'))
          setEditing(null)
        },
        onError: () => toast.error(t('common.errorDefault')),
      })
    } else {
      updateRule.mutate(
        { id: editing.id, body },
        {
          onSuccess: () => {
            toast.success(t('settings.alertRules.saved'))
            setEditing(null)
          },
          onError: () => toast.error(t('common.errorDefault')),
        },
      )
    }
  }

  function handleConfirmDelete() {
    if (!pendingDelete) return
    deleteRule.mutate(pendingDelete.id, {
      onSuccess: () => {
        toast.success(t('settings.alertRules.deleted'))
        setPendingDelete(null)
      },
      onError: () => {
        toast.error(t('common.errorDefault'))
        setPendingDelete(null)
      },
    })
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between gap-2">
        <p className="text-xs text-muted-foreground">{t('settings.alertRules.description')}</p>
        <Button type="button" variant="outline" size="sm" className="shrink-0 gap-1.5" onClick={() => setEditing('new')}>
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          {t('settings.alertRules.add')}
        </Button>
      </div>

      {query.isLoading ? (
        <Skeleton className="h-24 w-full" />
      ) : query.isError ? (
        <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
      ) : query.data && query.data.length === 0 ? (
        <p className="rounded-md border border-dashed border-border px-3 py-4 text-center text-xs text-muted-foreground">
          {t('settings.alertRules.empty')}
        </p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[640px] text-sm">
            <thead>
              <tr className="border-b border-border text-left text-xs text-muted-foreground">
                <th className="py-2 pr-3 font-medium">{t('settings.alertRules.colName')}</th>
                <th className="py-2 pr-3 font-medium">{t('settings.alertRules.colScope')}</th>
                <th className="py-2 pr-3 font-medium">{t('settings.alertRules.colMetric')}</th>
                <th className="py-2 pr-3 text-right font-medium">{t('settings.alertRules.colThreshold')}</th>
                <th className="py-2 pr-3 text-right font-medium">{t('settings.alertRules.colWindow')}</th>
                <th className="py-2 pr-3 font-medium">{t('settings.alertRules.colSeverity')}</th>
                <th className="py-2 pr-3 font-medium">{t('settings.alertRules.colEnabled')}</th>
                <th className="py-2 font-medium" />
              </tr>
            </thead>
            <tbody>
              {query.data?.map((rule) => (
                <tr key={rule.id} className="border-b border-border/50">
                  <td className="py-2 pr-3 font-medium text-foreground">{rule.name}</td>
                  <td className="py-2 pr-3 text-muted-foreground">{t(SCOPE_LABEL_KEYS[rule.scope])}</td>
                  <td className="py-2 pr-3 text-muted-foreground">{t(METRIC_LABEL_KEYS[rule.metric])}</td>
                  <td className="font-data py-2 pr-3 text-right">
                    {formatThreshold(rule.metric, rule.threshold)}
                  </td>
                  <td className="font-data py-2 pr-3 text-right">
                    {t('settings.alertRules.windowMinutesValue', { minutes: rule.window_minutes })}
                  </td>
                  <td className="py-2 pr-3">
                    <Badge variant={SEVERITY_BADGE_VARIANT[rule.severity]}>
                      {t(SEVERITY_LABEL_KEYS[rule.severity])}
                    </Badge>
                  </td>
                  <td className="py-2 pr-3 text-muted-foreground">
                    {rule.enabled ? t('common.yes') : t('common.no')}
                  </td>
                  <td className="py-2 text-right">
                    <div className="flex justify-end gap-1">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('common.edit')}
                        onClick={() => setEditing(rule)}
                      >
                        <Pencil className="h-3.5 w-3.5" aria-hidden="true" />
                      </Button>
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon-sm"
                        aria-label={t('common.delete')}
                        onClick={() => setPendingDelete(rule)}
                      >
                        <Trash2 className="h-3.5 w-3.5 text-destructive" aria-hidden="true" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {editing !== null && (
        <AlertRuleFormDialog
          initial={editing === 'new' ? null : editing}
          onOpenChange={(open) => !open && setEditing(null)}
          onSave={handleSave}
          saving={createRule.isPending || updateRule.isPending}
        />
      )}

      <Dialog open={pendingDelete !== null} onOpenChange={(open) => !open && setPendingDelete(null)}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>{t('settings.alertRules.deleteConfirmTitle')}</DialogTitle>
            <DialogDescription>
              {pendingDelete && t('settings.alertRules.deleteConfirmDescription', { name: pendingDelete.name })}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => setPendingDelete(null)}>
              {t('common.cancel')}
            </Button>
            <Button type="button" variant="destructive" onClick={handleConfirmDelete} disabled={deleteRule.isPending}>
              {t('common.delete')}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}

function AlertRuleFormDialog({
  initial,
  onOpenChange,
  onSave,
  saving,
}: {
  initial: AlertRuleOut | null
  onOpenChange: (open: boolean) => void
  onSave: (body: AlertRuleInput) => void
  saving: boolean
}) {
  const { t } = useTranslation()
  const [name, setName] = useState(initial?.name ?? '')
  const [scope, setScope] = useState<AlertRuleScope>(initial?.scope ?? 'client_ip')
  const [metric, setMetric] = useState<AlertRuleMetric>(initial?.metric ?? 'total_bytes')
  const [windowMinutes, setWindowMinutes] = useState(() => String(initial?.window_minutes ?? 10))
  const [thresholdInput, setThresholdInput] = useState(() => {
    if (!initial) return ''
    return isByteMetric(initial.metric) ? String(initial.threshold / 1_000_000) : String(initial.threshold)
  })
  const [severity, setSeverity] = useState<AnomalySeverity>(initial?.severity ?? 'high')
  const [enabled, setEnabled] = useState(initial?.enabled ?? true)

  function handleSubmit() {
    const minutes = Math.round(Number(windowMinutes))
    const rawThreshold = Number(thresholdInput)
    const threshold = isByteMetric(metric) ? Math.round(rawThreshold * 1_000_000) : Math.round(rawThreshold)
    if (!name.trim() || !Number.isFinite(minutes) || minutes < 1 || !Number.isFinite(rawThreshold) || threshold <= 0) {
      toast.error(t('common.errorDefault'))
      return
    }
    onSave({ name: name.trim(), scope, metric, window_minutes: minutes, threshold, severity, enabled })
  }

  return (
    <Dialog open onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>
            {initial ? t('settings.alertRules.editTitle') : t('settings.alertRules.addTitle')}
          </DialogTitle>
          <DialogDescription>{t('settings.alertRules.formDescription')}</DialogDescription>
        </DialogHeader>

        <div className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule-name">{t('settings.alertRules.colName')}</Label>
            <Input id="rule-name" value={name} onChange={(e) => setName(e.target.value)} maxLength={120} />
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rule-scope">{t('settings.alertRules.colScope')}</Label>
              <Select value={scope} onValueChange={(v) => setScope(v as AlertRuleScope)}>
                <SelectTrigger id="rule-scope" size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {SCOPE_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {t(SCOPE_LABEL_KEYS[option])}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rule-metric">{t('settings.alertRules.colMetric')}</Label>
              <Select value={metric} onValueChange={(v) => setMetric(v as AlertRuleMetric)}>
                <SelectTrigger id="rule-metric" size="sm">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {METRIC_OPTIONS.map((option) => (
                    <SelectItem key={option} value={option}>
                      {t(METRIC_LABEL_KEYS[option])}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
          </div>

          <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rule-threshold">
                {isByteMetric(metric)
                  ? t('settings.alertRules.thresholdMb')
                  : t('settings.alertRules.thresholdCount')}
              </Label>
              <Input
                id="rule-threshold"
                type="number"
                min={0}
                step={isByteMetric(metric) ? '0.1' : '1'}
                value={thresholdInput}
                onChange={(e) => setThresholdInput(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="rule-window">{t('settings.alertRules.colWindow')}</Label>
              <Input
                id="rule-window"
                type="number"
                min={1}
                max={1440}
                value={windowMinutes}
                onChange={(e) => setWindowMinutes(e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <Label htmlFor="rule-severity">{t('settings.alertRules.colSeverity')}</Label>
            <Select value={severity} onValueChange={(v) => setSeverity(v as AnomalySeverity)}>
              <SelectTrigger id="rule-severity" size="sm" className="w-40">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {SEVERITY_OPTIONS.map((option) => (
                  <SelectItem key={option} value={option}>
                    {t(SEVERITY_LABEL_KEYS[option])}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="flex items-center gap-2">
            <Checkbox id="rule-enabled" checked={enabled} onCheckedChange={(c) => setEnabled(c === true)} />
            <Label htmlFor="rule-enabled" className="font-normal">
              {t('settings.alertRules.colEnabled')}
            </Label>
          </div>
        </div>

        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => onOpenChange(false)}>
            {t('common.cancel')}
          </Button>
          <Button type="button" onClick={handleSubmit} disabled={saving}>
            {t('common.save')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
