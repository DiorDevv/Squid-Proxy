import { cn } from '@/lib/utils'
import { formatBytes, formatNumber } from '@/lib/format'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { ActorRow } from '@/types/api'

interface ActorLeaderboardProps {
  rows: ActorRow[]
  actorKind: string
  loading?: boolean
  sort: string
  onSortChange: (sort: string) => void
  onSelect: (row: ActorRow) => void
}

const COLS: { key: string; labelKey: TranslationKey; sortable: boolean; align?: 'right' }[] = [
  { key: 'actor', labelKey: 'analytics.who.colActor', sortable: false },
  { key: 'requests', labelKey: 'analytics.metric.totalRequests', sortable: true, align: 'right' },
  { key: 'blocked', labelKey: 'analytics.metric.blocked', sortable: true, align: 'right' },
  { key: 'blocked_ratio', labelKey: 'analytics.who.colBlockedPct', sortable: false, align: 'right' },
  { key: 'bytes', labelKey: 'analytics.metric.dataTransferred', sortable: true, align: 'right' },
  { key: 'top_category', labelKey: 'analytics.who.colTopCategory', sortable: false },
]

export function ActorLeaderboard({
  rows,
  actorKind,
  loading,
  sort,
  onSortChange,
  onSelect,
}: ActorLeaderboardProps) {
  const { t } = useTranslation()

  if (loading) {
    return <div className="h-64 w-full animate-pulse rounded-md bg-muted" />
  }
  if (rows.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.who.empty')}
      </div>
    )
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] text-sm">
        <thead>
          <tr className="border-b border-border text-left text-xs text-muted-foreground">
            {COLS.map((col) => (
              <th
                key={col.key}
                className={cn('py-2 pr-3 font-medium', col.align === 'right' && 'text-right')}
              >
                {col.key === 'actor'
                  ? actorKind === 'user'
                    ? t('analytics.who.colUser')
                    : t('analytics.who.colClientIp')
                  : col.sortable
                    ? (
                      <button
                        type="button"
                        onClick={() => onSortChange(col.key)}
                        className={cn(
                          'transition-colors hover:text-foreground',
                          sort === col.key && 'text-primary',
                        )}
                      >
                        {t(col.labelKey)}
                        {sort === col.key ? ' ↓' : ''}
                      </button>
                    )
                    : t(col.labelKey)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => {
            const ratioPct = row.blocked_ratio * 100
            return (
              <tr
                key={row.actor}
                onClick={() => onSelect(row)}
                className="cursor-pointer border-b border-border/50 transition-colors hover:bg-secondary/40"
              >
                <td className="font-data py-2 pr-3 font-medium text-foreground">{row.actor}</td>
                <td className="font-data py-2 pr-3 text-right">{formatNumber(row.request_count)}</td>
                <td className="font-data py-2 pr-3 text-right">{formatNumber(row.blocked_count)}</td>
                <td
                  className={cn(
                    'font-data py-2 pr-3 text-right',
                    ratioPct >= 40 ? 'text-destructive' : ratioPct >= 15 ? 'text-amber-500' : 'text-muted-foreground',
                  )}
                >
                  {ratioPct.toFixed(1)}%
                </td>
                <td className="font-data py-2 pr-3 text-right">{formatBytes(row.total_bytes)}</td>
                <td className="py-2 pr-3">
                  {row.top_category ? (
                    <span className="inline-flex items-center gap-1.5">
                      <span
                        className="h-2 w-2 shrink-0 rounded-full"
                        style={{ backgroundColor: CATEGORY_COLORS[row.top_category] }}
                        aria-hidden="true"
                      />
                      {t(CATEGORY_LABEL_KEYS[row.top_category])}
                    </span>
                  ) : (
                    <span className="text-muted-foreground">—</span>
                  )}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
