import { useState } from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { ErrorState } from '@/components/common/ErrorState'
import { useAlertSettings, useTestTelegramAlert, useUpdateAlertSettings } from '@/hooks/useAlertSettings'
import { useBranches } from '@/hooks/useBranches'
import { ApiError } from '@/lib/api-client'
import { CATEGORY_LABEL_KEYS, CATEGORY_OPTIONS } from '@/lib/categories'
import { useTranslation } from '@/i18n'
import type { AlertSettingsOut, DomainCategoryLabel } from '@/types/api'

const BYTES_PER_GB = 1_000_000_000
const DEFAULT_BRANCH = 'default'

/** Admin-tunable thresholds for the category/quota anomaly checks (see
 * backend app/services/alert_settings_service.py) -- who gets flagged for
 * visiting a sensitive category for the first time, spending too long in
 * non-work categories per day, or exceeding a daily data quota. All three
 * are opt-in: empty/zero/unset means that check stays off.
 *
 * Thresholds are per-branch: this panel edits one branch's settings at a
 * time (independent of the dashboard-wide branch filter in
 * lib/filters-store.ts -- picking a branch here to *edit* shouldn't also
 * change what data the rest of the app is *viewing*), defaulting to the
 * first configured branch. */
export function AlertSettingsPanel() {
  const { t } = useTranslation()
  const branches = useBranches()
  const branchItems = branches.data?.items ?? []

  // Derived, not synced via effect: `manualBranch` is only the admin's
  // explicit pick, if any and still valid; otherwise the first configured
  // branch (or the single-branch default before the list has loaded).
  const [manualBranch, setManualBranch] = useState<string | null>(null)
  const branch =
    manualBranch && branchItems.some((item) => item.slug === manualBranch)
      ? manualBranch
      : (branchItems[0]?.slug ?? DEFAULT_BRANCH)

  const query = useAlertSettings(branch)

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

  // Narrows query.data from `AlertSettingsOut | undefined` for the render
  // below -- isLoading/isError already rule this out in practice, but
  // TypeScript can't infer that across separate boolean flags.
  if (!query.data) {
    return null
  }

  return (
    <div className="flex flex-col gap-4">
      {branchItems.length > 1 && (
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="alert-settings-branch">{t('branch.filter')}</Label>
          <Select value={branch} onValueChange={setManualBranch}>
            <SelectTrigger id="alert-settings-branch" size="sm" className="w-48">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {branchItems.map((item) => (
                <SelectItem key={item.slug} value={item.slug}>
                  {item.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}

      {/* key={branch} remounts the form fresh whenever the branch changes,
          so its local state is (re-)initialized straight from that branch's
          data with no effect needed -- also means an in-progress edit for
          the current branch survives an incidental background refetch. */}
      <AlertSettingsForm key={branch} branch={branch} data={query.data} />
    </div>
  )
}

function AlertSettingsForm({ branch, data }: { branch: string; data: AlertSettingsOut }) {
  const { t } = useTranslation()
  const updateSettings = useUpdateAlertSettings(branch)
  const testTelegramAlert = useTestTelegramAlert(branch)

  const [sensitiveCategories, setSensitiveCategories] = useState<Set<DomainCategoryLabel>>(
    () => new Set(data.sensitive_categories),
  )
  const [nonWorkMinutes, setNonWorkMinutes] = useState(() => String(data.non_work_minutes_threshold))
  const [quotaGb, setQuotaGb] = useState(() =>
    data.client_daily_byte_quota_bytes != null ? String(data.client_daily_byte_quota_bytes / BYTES_PER_GB) : '',
  )
  const [uncategorizedThreshold, setUncategorizedThreshold] = useState(() =>
    data.uncategorized_domain_request_threshold != null ? String(data.uncategorized_domain_request_threshold) : '',
  )
  const [telegramChatId, setTelegramChatId] = useState(() => data.telegram_chat_id ?? '')

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
    const trimmedUncategorized = uncategorizedThreshold.trim()
    const uncategorizedValue = trimmedUncategorized ? Math.round(Number(trimmedUncategorized)) : null
    const uncategorizedIsInvalid =
      trimmedUncategorized !== '' && !Number.isFinite(Number(trimmedUncategorized))
    if (!Number.isFinite(minutes) || minutes < 0 || quotaIsInvalid || uncategorizedIsInvalid) {
      toast.error(t('common.errorDefault'))
      return
    }

    updateSettings.mutate(
      {
        sensitive_categories: Array.from(sensitiveCategories),
        non_work_minutes_threshold: minutes,
        client_daily_byte_quota_bytes: quota,
        uncategorized_domain_request_threshold: uncategorizedValue,
        telegram_chat_id: telegramChatId.trim() || null,
      },
      {
        onSuccess: () => toast.success(t('settings.alertSettingsSaved')),
        onError: () => toast.error(t('common.errorDefault')),
      },
    )
  }

  function handleTestTelegram() {
    const chatId = telegramChatId.trim()
    if (!chatId) return
    testTelegramAlert.mutate(chatId, {
      onSuccess: () => toast.success(t('settings.telegramTestSent')),
      onError: (err) => toast.error(err instanceof ApiError ? err.message : t('settings.telegramTestFailed')),
    })
  }

  return (
    <>
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
        <div className="flex flex-col gap-1.5">
          <Label htmlFor="uncategorized-threshold">{t('settings.uncategorizedDomainThreshold')}</Label>
          <Input
            id="uncategorized-threshold"
            type="number"
            min={0}
            placeholder={t('settings.uncategorizedDomainThresholdPlaceholder')}
            value={uncategorizedThreshold}
            onChange={(e) => setUncategorizedThreshold(e.target.value)}
          />
          <p className="text-xs text-muted-foreground">{t('settings.uncategorizedDomainThresholdDescription')}</p>
        </div>
      </div>

      <div className="flex flex-col gap-1.5">
        <Label htmlFor="telegram-chat-id">{t('settings.telegramChatId')}</Label>
        <div className="flex gap-2">
          <Input
            id="telegram-chat-id"
            placeholder={t('settings.telegramChatIdPlaceholder')}
            value={telegramChatId}
            onChange={(e) => setTelegramChatId(e.target.value)}
            className="max-w-xs"
          />
          <Button
            type="button"
            variant="outline"
            onClick={handleTestTelegram}
            disabled={!telegramChatId.trim() || testTelegramAlert.isPending}
          >
            {t('settings.telegramTestSend')}
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">{t('settings.telegramChatIdDescription')}</p>
      </div>

      <Button onClick={handleSave} disabled={updateSettings.isPending} className="w-fit">
        {t('common.save')}
      </Button>
    </>
  )
}
