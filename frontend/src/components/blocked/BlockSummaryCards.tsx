import { StackedAreaOverTime } from '@/components/analytics/StackedAreaOverTime'
import { formatNumber } from '@/lib/format'
import { useTranslation, type TranslationKey } from '@/i18n'
import { cn } from '@/lib/utils'
import type { BlockSummary } from '@/types/api'

// Validated pair (dataviz validate_palette, light + dark): real block vs 407.
const SERIES_COLORS: Record<string, string> = { denied: '#ef4444', auth: '#3b82f6' }

function Stat({
  labelKey,
  value,
  hint,
  swatch,
}: {
  labelKey: TranslationKey
  value: string
  hint?: string
  swatch?: string
}) {
  const { t } = useTranslation()
  return (
    <div className="flex min-w-0 flex-col gap-1 rounded-md border border-border bg-secondary/30 px-3 py-2">
      <span className="flex items-center gap-1.5 truncate text-[11px] font-medium uppercase text-muted-foreground">
        {swatch && <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: swatch }} aria-hidden="true" />}
        {t(labelKey)}
      </span>
      <span className="font-data text-xl font-semibold text-foreground">{value}</span>
      {hint && (
        <span className="font-data truncate text-[11px] text-muted-foreground" title={hint}>
          {hint}
        </span>
      )}
    </div>
  )
}

export function BlockSummaryCards({ summary, loading }: { summary?: BlockSummary; loading: boolean }) {
  const { t } = useTranslation()
  if (loading && !summary) {
    return <div className="h-64 w-full animate-pulse rounded-md bg-muted" />
  }
  const s = summary
  const n = (value: number | undefined) => (value === undefined ? '—' : formatNumber(value))
  return (
    <div className={cn('flex flex-col gap-3', loading && 'opacity-60')}>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
        <Stat labelKey="blocked.summary.domains" value={n(s?.domains)} />
        <Stat labelKey="blocked.summary.denied" value={n(s?.denied)} swatch={SERIES_COLORS.denied} />
        <Stat labelKey="blocked.summary.auth" value={n(s?.auth)} swatch={SERIES_COLORS.auth} />
        <Stat labelKey="blocked.summary.clients" value={n(s?.clients)} />
        <Stat labelKey="blocked.summary.users" value={n(s?.users)} />
        <Stat
          labelKey="blocked.summary.where"
          value={`${n(s?.branches.length)} / ${n(s?.proxies.length)}`}
          hint={s ? [...s.branches, ...s.proxies].join(', ') || undefined : undefined}
        />
      </div>
      <StackedAreaOverTime
        rows={(s?.series ?? []).map((p) => ({ bucket_ts: p.bucket_ts, values: { denied: p.denied, auth: p.auth } }))}
        labels={['denied', 'auth']}
        granularity="hour"
        colorFor={(label) => SERIES_COLORS[label] ?? '#ef4444'}
        labelFor={(label) => t(label === 'denied' ? 'blocked.summary.denied' : 'blocked.summary.auth')}
        height={180}
        emptyText={t('blocked.analysis.empty')}
      />
    </div>
  )
}
