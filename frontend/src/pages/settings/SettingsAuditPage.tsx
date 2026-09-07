import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { AuditLogPanel } from '@/components/settings/AuditLogPanel'
import { useTranslation } from '@/i18n'

/** The who-did-what and who-looked-at-whom trail. Its own sub-page (not
 * folded into Users) because the `auditor` role can see this and nothing
 * else mutable under Settings. */
export default function SettingsAuditPage() {
  const { t } = useTranslation()

  return (
    <div className="flex flex-col gap-4">
      <Panel title={t('settings.auditLog')}>
        <PanelErrorBoundary panelLabel={t('settings.auditLog')}>
          <AuditLogPanel />
        </PanelErrorBoundary>
      </Panel>
    </div>
  )
}
