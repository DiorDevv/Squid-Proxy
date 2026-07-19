import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { useAlertSettings, useUpdateAlertSettings } from '@/hooks/useAlertSettings'
import { CATEGORY_LABEL_KEYS, CATEGORY_OPTIONS } from '@/lib/categories'
import { useTranslation } from '@/i18n'
import type { DomainCategoryLabel } from '@/types/api'

const BYTES_PER_GB = 1_000_000_000

/** Admin-tunable thresholds for the category/quota anomaly checks (see
 * backend app/services/alert_settings_service.py) -- who gets flagged for
 * visiting a sensitive category for the first time, spending too long in
 * non-work categories per day, or exceeding a daily data quota. All three
 * are opt-in: empty/zero/unset means that check stays off. */
export function AlertSettingsPanel() {
  const { t } = useTranslation()
  const query = useAlertSettings()
  const updateSettings = useUpdateAlertSettings()

  const [sensitiveCategories, setSensitiveCategories] = useState<Set<DomainCategoryLabel>>(new Set())
  const [nonWorkMinutes, setNonWorkMinutes] = useState('120')
  const [quotaGb, setQuotaGb] = useState('')

  useEffect(() => {
    if (!query.data) return
    setSensitiveCategories(new Set(query.data.sensitive_categories))
    setNonWorkMinutes(String(query.data.non_work_minutes_threshold))
    setQuotaGb(
      query.data.client_daily_byte_quota_bytes != null
        ? String(query.data.client_daily_byte_quota_bytes / BYTES_PER_GB)
        : '',
    )
  }, [query.data])

  function setCategoryChecked(category: DomainCategoryLabel, checked: boolean) {
    setSensitiveCategories((prev) => {
      const next = new Set(prev)
      if (checked) next.add(category)
      else next.delete(category)
      return next
    })
  }

  function handleSave() {
    const minutes = Number(nonWorkMinutes)
    const trimmedQuota = quotaGb.trim()
    const quota = trimmedQuota ? Math.round(Number(trimmedQuota) * BYTES_PER_GB) : null
    const quotaIsInvalid = trimmedQuota !== '' && !Number.isFinite(Number(trimmedQuota))
    if (!Number.isFinite(minutes) || minutes < 0 || quotaIsInvalid) {
      toast.error(t('common.errorDefault'))
      return
    }

    updateSettings.mutate(
      {
        sensitive_categories: Array.from(sensitiveCategories),
        non_work_minutes_threshold: minutes,
        client_daily_byte_quota_bytes: quota,
      },
      {
        onSuccess: () => toast.success(t('settings.alertSettingsSaved')),
        onError: () => toast.error(t('common.errorDefault')),
      },
    )
  }

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-9 w-full" />
        ))}
      </div>
    )
  }

  if (query.isError) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-col gap-2">
        <Label>{t('settings.sensitiveCategories')}</Label>
        <p className="text-xs text-muted-foreground">{t('settings.sensitiveCategoriesDescription')}</p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {CATEGORY_OPTIONS.filter((category) => category !== 'uncategorized').map((category) => (
            <div key={category} className="flex items-center gap-2">
              <Checkbox
                id={`sensitive-${category}`}
                checked={sensitiveCategories.has(category)}
                onCheckedChange={(checked) => setCategoryChecked(category, checked === true)}
              />
              <Label htmlFor={`sensitive-${category}`} className="font-normal">
                {t(CATEGORY_LABEL_KEYS[category])}
              </Label>
            </div>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="non-work-minutes">{t('settings.nonWorkMinutesThreshold')}</Label>
          <Input
            id="non-work-minutes"
            type="number"
            min={0}
            value={nonWorkMinutes}
            onChange={(e) => setNonWorkMinutes(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('settings.nonWorkMinutesDescription')}</p>
        </div>
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="client-quota">{t('settings.clientDailyQuota')}</Label>
          <Input
            id="client-quota"
            type="number"
            min={0}
            step="0.1"
            placeholder={t('settings.clientDailyQuotaPlaceholder')}
            value={quotaGb}
            onChange={(e) => setQuotaGb(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('settings.clientDailyQuotaDescription')}</p>
        </div>
      </div>

      <Button onClick={handleSave} disabled={updateSettings.isPending} className="w-fit">
        {t('common.save')}
      </Button>
    </div>
  )
}
