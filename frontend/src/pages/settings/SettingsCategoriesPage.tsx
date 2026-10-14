import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { DomainCategoriesPanel } from '@/components/settings/DomainCategoriesPanel'
import { AlertSettingsPanel } from '@/components/settings/AlertSettingsPanel'
import { ReportsPanel } from '@/components/settings/ReportsPanel'
import { useHasPermission } from '@/lib/auth-store'
import { useTranslation } from '@/i18n'

export default function SettingsCategoriesPage() {
  const { t } = useTranslation()
  // The page opens to anyone holding one of these; each panel shows only
  // to whoever holds its own permission.
  const canCategories = useHasPermission('categories')
  const canAlerts = useHasPermission('alerts')
  const canReports = useHasPermission('reports')

  return (
    <div className="flex flex-col gap-4">
      {canCategories && (
        <Panel title={t('settings.domainCategories')}>
          <PanelErrorBoundary panelLabel={t('settings.domainCategories')}>
            <DomainCategoriesPanel />
          </PanelErrorBoundary>
        </Panel>
      )}

      {canAlerts && (
        <Panel title={t('settings.alertSettings')}>
          <PanelErrorBoundary panelLabel={t('settings.alertSettings')}>
            <AlertSettingsPanel />
          </PanelErrorBoundary>
        </Panel>
      )}

      {canReports && (
        <Panel title={t('settings.reports')}>
          <PanelErrorBoundary panelLabel={t('settings.reports')}>
            <ReportsPanel />
          </PanelErrorBoundary>
        </Panel>
      )}
    </div>
  )
}
