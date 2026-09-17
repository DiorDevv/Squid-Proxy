import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { UserManagementPanel } from '@/components/settings/UserManagementPanel'
import { useTranslation } from '@/i18n'

export default function SettingsUsersPage() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('settings.userManagement')}>
        <PanelErrorBoundary panelLabel={t('settings.userManagement')}>
          <UserManagementPanel />
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
