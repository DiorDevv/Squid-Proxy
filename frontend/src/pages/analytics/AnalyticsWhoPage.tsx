import { useState } from 'react'
import { Panel } from '@/components/common/Panel'
import { PanelErrorBoundary } from '@/components/common/PanelErrorBoundary'
import { ErrorState } from '@/components/common/ErrorState'
import { ActorLeaderboard } from '@/components/analytics/ActorLeaderboard'
import { ActorDetailSheet } from '@/components/analytics/ActorDetailSheet'
import { formatNumber } from '@/lib/format'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useActorLeaderboard, useNewEntities } from '@/hooks/useAnalytics'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { ActorRow } from '@/types/api'

function NewList({ titleKey, items, total }: { titleKey: TranslationKey; items: string[]; total: number }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col gap-1.5">
      <div className="flex items-baseline justify-between">
        <h3 className="text-xs font-semibold uppercase text-muted-foreground">{t(titleKey)}</h3>
        <span className="font-data text-xs text-muted-foreground">{formatNumber(total)}</span>
      </div>
      {items.length === 0 ? (
        <p className="text-xs text-muted-foreground">{t('analytics.who.noneNew')}</p>
      ) : (
        <ul className="scrollbar-thin flex max-h-48 flex-col gap-0.5 overflow-y-auto">
          {items.map((v) => (
            <li key={v} className="font-data truncate text-sm text-foreground">
              {v}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

export default function AnalyticsWhoPage() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const [sort, setSort] = useState('requests')
  const [selected, setSelected] = useState<ActorRow | null>(null)

  const board = useActorLeaderboard(rangeParams, sort, 50, true)
  const newEntities = useNewEntities(rangeParams, true)

  return (
    <div className="flex flex-col gap-4">
      <Panel
        title={t('analytics.who.title')}
        action={<span className="text-xs text-muted-foreground">{t('analytics.who.hint')}</span>}
      >
        <PanelErrorBoundary panelLabel={t('analytics.who.title')}>
          {board.isError ? (
            <ErrorState message={board.error?.message} onRetry={() => board.refetch()} />
          ) : (
            <ActorLeaderboard
              rows={board.data?.rows ?? []}
              actorKind={board.data?.actor_kind ?? 'user'}
              loading={board.isLoading}
              sort={sort}
              onSortChange={setSort}
              onSelect={setSelected}
            />
          )}
        </PanelErrorBoundary>
      </Panel>

      <Panel
        title={t('analytics.who.newThisPeriod')}
        action={<span className="text-xs text-muted-foreground">{t('analytics.movers.hint')}</span>}
      >
        <PanelErrorBoundary panelLabel={t('analytics.who.newThisPeriod')}>
          {newEntities.isLoading ? (
            <div className="h-40 animate-pulse rounded bg-muted" />
          ) : (
            <div className="grid grid-cols-1 gap-6 sm:grid-cols-3">
              <NewList
                titleKey="analytics.who.newUsers"
                items={newEntities.data?.new_users ?? []}
                total={newEntities.data?.new_users_total ?? 0}
              />
              <NewList
                titleKey="analytics.who.newClients"
                items={newEntities.data?.new_clients ?? []}
                total={newEntities.data?.new_clients_total ?? 0}
              />
              <NewList
                titleKey="analytics.who.newDomains"
                items={newEntities.data?.new_domains ?? []}
                total={newEntities.data?.new_domains_total ?? 0}
              />
            </div>
          )}
        </PanelErrorBoundary>
      </Panel>

      <ActorDetailSheet
        actor={selected}
        rangeParams={rangeParams}
        onOpenChange={(open) => !open && setSelected(null)}
      />
    </div>
  )
}
