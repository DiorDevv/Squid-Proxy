import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { TelegramLinkDialog } from '@/components/settings/TelegramLinkDialog'
import {
  useCreateSuperAdminTelegramLinkCode,
  useInvalidateTelegramLinkTarget,
  useSuperAdminTelegram,
  useTelegramLinkFlow,
  useTelegramLinkStatus,
} from '@/hooks/useTelegramLink'
import { useTranslation } from '@/i18n'

/** The super-admin's global Telegram chat (see backend
 * app/models/telegram_global_settings.py) -- every branch's alerts go
 * here in addition to that branch's own chat (AlertSettingsPanel). Only
 * ever rendered for an unrestricted admin, see SettingsTelegramPage. */
export function SuperAdminTelegramPanel() {
  const { t } = useTranslation()
  const query = useSuperAdminTelegram()
  const createTelegramLinkCode = useCreateSuperAdminTelegramLinkCode()
  const { invalidateSuperAdmin } = useInvalidateTelegramLinkTarget()
  const telegramLink = useTelegramLinkFlow(() => createTelegramLinkCode.mutateAsync())

  if (query.isLoading) {
    return <Skeleton className="h-9 w-full" />
  }

  if (query.isError) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }

  if (!query.data) {
    return null
  }

  const chatId = query.data.chat_id

  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="text-sm text-muted-foreground">
          {chatId ? `✅ ${t('settings.telegramLink.connected')}` : `❌ ${t('settings.telegramLink.notConnected')}`}
        </span>
        <Button type="button" variant="outline" size="sm" onClick={telegramLink.connect}>
          {chatId ? t('settings.telegramLink.reconnect') : t('settings.telegramLink.connect')}
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">{t('settings.superAdminTelegram.description')}</p>

      <TelegramLinkDialog
        open={telegramLink.open}
        onOpenChange={telegramLink.handleOpenChange}
        title={t('settings.telegramLink.dialogTitle')}
        instructions={t('settings.telegramLink.dialogInstructions')}
        code={telegramLink.code}
        onRequestNewCode={telegramLink.requestNewCode}
        useStatus={useTelegramLinkStatus}
        onLinked={() => invalidateSuperAdmin()}
      />
    </div>
  )
}
