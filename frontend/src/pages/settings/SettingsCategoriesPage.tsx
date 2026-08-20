import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { DomainCategoriesPanel } from '@/components/settings/DomainCategoriesPanel'
import { AlertSettingsPanel } from '@/components/settings/AlertSettingsPanel'
import { ReportsPanel } from '@/components/settings/ReportsPanel'
import { useTranslation } from '@/i18n'

export default function SettingsCategoriesPage() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-4">
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
    </div>
  )
}
