import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatNumber } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { BranchTrendResponse, TrendGranularity } from '@/types/api'

const ALLOWED = '#22c55e'
const BLOCKED = '#ef4444'

interface BranchTrendGridProps {
  data?: BranchTrendResponse
  loading?: boolean
}

function formatBucket(iso: string, granularity: TrendGranularity): string {
  const date = new Date(iso)
  if (granularity === 'day') {
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit' }).format(date)
  }
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit', hour: '2-digit', hour12: false }).format(
    date,
  )
}

/** One small requests-over-time chart per branch (allowed/blocked stacked),
 * side by side -- the "which branch is doing what, and when" view that a
 * single snapshot comparison (see BranchComparisonChart) can't answer. A
 * branch configured but silent in this range still gets its own tile, with
 * an explicit "no traffic" state instead of just being absent. */
export function BranchTrendGrid({ data, loading }: BranchTrendGridProps) {
  const { t } = useTranslation()

  if (loading) {
    return (
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <div key={i} className="h-48 w-full animate-pulse rounded-md bg-muted" />
        ))}
      </div>
    )
  }

  if (!data || data.series.length === 0) {
    return (
      <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.branches.empty')}
      </div>
    )
  }

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
      {data.series.map((series) => {
        const totalRequests = series.points.reduce((sum, p) => sum + p.total_requests, 0)
        const totalBlocked = series.points.reduce((sum, p) => sum + p.blocked_requests, 0)
        return (
          <div key={series.branch} className="rounded-lg border border-border p-3">
            <div className="mb-2 flex items-baseline justify-between gap-2">
              <span className="min-w-0 truncate text-sm font-medium text-foreground" title={series.branch}>
                {series.branch}
              </span>
              <span className="font-data shrink-0 text-xs text-muted-foreground">
                {formatNumber(totalRequests)}
                {totalBlocked > 0 && (
                  <span className="text-destructive">
                    {' '}
                    · {formatNumber(totalBlocked)} {t('analytics.metric.blocked').toLowerCase()}
                  </span>
                )}
              </span>
            </div>
            {series.points.length === 0 ? (
              <div className="flex h-36 items-center justify-center text-xs text-muted-foreground">
                {t('analytics.branches.trendBranchEmpty')}
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={144}>
                <AreaChart data={series.points} margin={{ top: 4, right: 4, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="bucket_ts"
                    tickFormatter={(value: string) => formatBucket(value, data.granularity)}
                    tick={{ fill: 'var(--color-muted-foreground)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    axisLine={{ stroke: 'var(--color-border)' }}
                    tickLine={false}
                    minTickGap={40}
                  />
                  <YAxis
                    tick={{ fill: 'var(--color-muted-foreground)', fontSize: 10, fontFamily: 'var(--font-mono)' }}
                    axisLine={false}
                    tickLine={false}
                    width={36}
                    tickFormatter={(value: number) => formatNumber(value)}
                  />
                  <Tooltip
                    contentStyle={{
                      background: 'var(--color-card)',
                      border: '1px solid var(--color-border)',
                      borderRadius: 'var(--radius-md)',
                      fontSize: 12,
                    }}
                    labelStyle={{ color: 'var(--color-muted-foreground)', fontFamily: 'var(--font-mono)' }}
                    labelFormatter={(value) => formatBucket(String(value), data.granularity)}
                    formatter={(value, name) => [
                      formatNumber(Number(value)),
                      name === 'allowed_requests' ? t('analytics.metric.allowed') : t('analytics.metric.blocked'),
                    ]}
                  />
                  <Area
                    type="monotone"
                    dataKey="allowed_requests"
                    stackId="1"
                    stroke={ALLOWED}
                    fill={ALLOWED}
                    fillOpacity={0.35}
                    strokeWidth={1.5}
                    isAnimationActive={false}
                  />
                  <Area
                    type="monotone"
                    dataKey="blocked_requests"
                    stackId="1"
                    stroke={BLOCKED}
                    fill={BLOCKED}
                    fillOpacity={0.35}
                    strokeWidth={1.5}
                    isAnimationActive={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            )}
          </div>
        )
      })}
    </div>
  )
}
