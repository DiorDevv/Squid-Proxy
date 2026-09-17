import { Info } from 'lucide-react'
import { useFiltersStore } from '@/lib/filters-store'
import { useRetention } from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'

/** The per-minute operational aggregates behind Traffic & Blocks are kept
 * a shorter time than the core aggregates (RETENTION_DAYS_OPS_AGGREGATES,
 * default 90d). A custom range that starts before that cutoff would show a
 * silently truncated series -- this makes that explicit. Renders nothing
 * for the 1h/24h/7d presets, which can never reach past it. */
export function OpsRetentionNote() {
  const { t } = useTranslation()
  const mode = useFiltersStore((s) => s.mode)
  const customFrom = useFiltersStore((s) => s.customFrom)
  const retention = useRetention()

  const opsDays = retention.data?.ops_aggregate_days
  if (mode !== 'custom' || !customFrom || !opsDays) return null

  // One-shot wall-clock read to decide whether this note applies; a minute
  // of staleness is irrelevant to a 90-day retention boundary.
  // eslint-disable-next-line react-hooks/purity
  const rangeStartsBeforeCutoff = new Date(customFrom).getTime() < Date.now() - opsDays * 86_400_000
  if (!rangeStartsBeforeCutoff) return null

  return (
    <div className="flex items-center gap-2 rounded-md border border-border bg-secondary/40 px-3 py-2 text-xs text-muted-foreground">
      <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
      {t('analytics.opsRetentionNote', { days: opsDays })}
    </div>
  )
}
