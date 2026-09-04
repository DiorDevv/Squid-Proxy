import { MiniStat } from '@/components/analytics/MiniStat'
import { formatNumber } from '@/lib/format'
import { resultCodeColor } from '@/lib/ops-colors'
import { useRangeSearchParams } from '@/lib/filters-store'
import { useResponseTime, useResultCodes } from '@/hooks/useAnalytics'
import { useTranslation } from '@/i18n'

const pct = (v: number | null | undefined) => (v == null ? '—' : `${(v * 100).toFixed(1)}%`)
const ms = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`)

/** One-glance Squid operational health for the Overview tab: cache
 * effectiveness, deny/tunnel share, tail latency, server errors -- plus
 * the result-code mix as a single stacked bar. */
export function SquidHealthStrip() {
  const { t } = useTranslation()
  const rangeParams = useRangeSearchParams()
  const codes = useResultCodes(rangeParams, 'hour', true)
  const rt = useResponseTime(rangeParams, 'hour', true)

  const c = codes.data
  const totalReq = c?.codes.reduce((s, x) => s + x.request_count, 0) ?? 0

  return (
    <div className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5">
        <MiniStat
          label={t('analytics.traffic.hitRatio')}
          value={pct(c?.hit_ratio)}
          tone={c?.hit_ratio != null && c.hit_ratio >= 0.3 ? 'good' : 'default'}
        />
        <MiniStat
          label={t('analytics.traffic.deniedRatio')}
          value={pct(c?.denied_ratio)}
          tone={c && c.denied_ratio >= 0.1 ? 'warn' : 'default'}
        />
        <MiniStat label={t('analytics.traffic.tunnelRatio')} value={pct(c?.tunnel_ratio)} />
        <MiniStat
          label={t('analytics.traffic.p95')}
          value={rt.data ? ms(rt.data.overall_p95) : '—'}
          tone={rt.data && rt.data.overall_p95 >= 3000 ? 'warn' : 'default'}
        />
        <MiniStat
          label={t('analytics.traffic.p99')}
          value={rt.data ? ms(rt.data.overall_p99) : '—'}
          tone={rt.data && rt.data.overall_p99 >= 10000 ? 'bad' : 'default'}
          hint={rt.data ? t('analytics.traffic.samples', { count: formatNumber(rt.data.sample_count) }) : undefined}
        />
      </div>

      {totalReq > 0 && (
        <div className="flex h-3 overflow-hidden rounded-full bg-muted" title={t('analytics.traffic.resultMix')}>
          {c?.codes.map((code) => (
            <div
              key={code.label}
              style={{ width: `${(code.request_count / totalReq) * 100}%`, backgroundColor: resultCodeColor(code.label) }}
              title={`${code.label}: ${code.pct.toFixed(1)}%`}
            />
          ))}
        </div>
      )}
    </div>
  )
}
