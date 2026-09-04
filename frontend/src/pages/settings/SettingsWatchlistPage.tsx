import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { WatchlistPanel } from '@/components/settings/WatchlistPanel'
import { useTranslation } from '@/i18n'

export default function SettingsWatchlistPage() {
  const { t } = useTranslation()
  return (
    <Panel title={t('watchlist.title')}>
      <PanelErrorBoundary panelLabel={t('watchlist.title')}>
        <WatchlistPanel />
      </PanelErrorBoundary>
    </Panel>
  )
}
