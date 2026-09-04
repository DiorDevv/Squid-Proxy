import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useTranslation } from '@/i18n'
import type { ResponseTimePoint, TrendGranularity } from '@/types/api'

interface ResponseTimeChartProps {
  points: ResponseTimePoint[]
  granularity: TrendGranularity
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

const fmtMs = (v: number) => (v >= 1000 ? `${(v / 1000).toFixed(1)}s` : `${Math.round(v)}ms`)

export function ResponseTimeChart({ points, granularity, loading }: ResponseTimeChartProps) {
  const { t } = useTranslation()
  if (loading) {
    return <div className="h-64 w-full animate-pulse rounded-md bg-muted" />
  }
  if (points.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.trend.empty')}
      </div>
    )
  }
  const data = points.map((p) => ({ ts: p.bucket_ts, p50: p.p50, p95: p.p95, p99: p.p99 }))
  return (
    <ResponsiveContainer width="100%" height={264}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
        <XAxis
          dataKey="ts"
          tickFormatter={(v: string) => formatBucket(v, granularity)}
          tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'var(--color-border)' }}
          tickLine={false}
          minTickGap={44}
        />
        <YAxis
          tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
          width={52}
          tickFormatter={fmtMs}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--color-card)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
            fontSize: 12,
          }}
          labelStyle={{ color: 'var(--color-muted-foreground)', fontFamily: 'var(--font-mono)' }}
          labelFormatter={(v) => formatBucket(String(v), granularity)}
          formatter={(value, name) => [fmtMs(Number(value)), String(name).toUpperCase()]}
        />
        <Line type="monotone" dataKey="p50" stroke="#22c55e" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="p95" stroke="#f59e0b" strokeWidth={2} dot={false} isAnimationActive={false} />
        <Line type="monotone" dataKey="p99" stroke="#ef4444" strokeWidth={2} dot={false} isAnimationActive={false} />
      </LineChart>
    </ResponsiveContainer>
  )
}
