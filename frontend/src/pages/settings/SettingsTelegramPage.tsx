import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { SuperAdminTelegramPanel } from '@/components/settings/SuperAdminTelegramPanel'
import { useAuth } from '@/hooks/useAuth'
import { useTranslation } from '@/i18n'

/** Super-admin-only page for linking the global Telegram chat (see
 * app/models/telegram_global_settings.py) that every branch's alerts also
 * go to. Hidden from a branch-scoped admin's side nav (see
 * SettingsLayout.tsx), but a direct URL hit must still not silently
 * expose or no-op this -- the backend independently enforces the same
 * restriction on every telegram-link/super-admin/telegram-super-admin
 * endpoint regardless of what this page shows. */
export default function SettingsTelegramPage() {
  const { t } = useTranslation()
  const { branch } = useAuth()

  if (branch !== null) {
    return <p className="text-sm text-muted-foreground">{t('settings.superAdminTelegram.notAuthorized')}</p>
  }

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('settings.superAdminTelegram.title')}>
        <PanelErrorBoundary panelLabel={t('settings.superAdminTelegram.title')}>
          <SuperAdminTelegramPanel />
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
