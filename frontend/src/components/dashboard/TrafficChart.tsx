import {
  Area,
  AreaChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import { formatNumber, formatTime } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { TimeseriesPoint } from '@/types/api'

interface TrafficChartProps {
  points: TimeseriesPoint[]
  loading?: boolean
}

const SUCCESS = '#22c55e'
const WARNING = '#f5a524'
const WARNING_DEEP = '#f97316'

export function TrafficChart({ points, loading }: TrafficChartProps) {
  const { t } = useTranslation()

  if (loading) {
    return <div className="h-72 w-full animate-pulse rounded-md bg-muted" />
  }

  if (points.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center text-sm text-muted-foreground">
        {t('dashboard.trafficEmpty')}
      </div>
    )
  }

  const data = points.map((p) => ({
    ts: p.bucket_ts,
    allowed: p.allowed_requests,
    blocked: p.blocked_requests,
  }))

  return (
    <ResponsiveContainer width="100%" height={288}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="allowedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={SUCCESS} stopOpacity={0.5} />
            <stop offset="100%" stopColor={SUCCESS} stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="blockedFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={WARNING} stopOpacity={0.5} />
            <stop offset="100%" stopColor={WARNING_DEEP} stopOpacity={0.02} />
          </linearGradient>
          <linearGradient id="allowedStroke" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={SUCCESS} />
            <stop offset="100%" stopColor="#14b8a6" />
          </linearGradient>
          <linearGradient id="blockedStroke" x1="0" y1="0" x2="1" y2="0">
            <stop offset="0%" stopColor={WARNING} />
            <stop offset="100%" stopColor={WARNING_DEEP} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
        <XAxis
          dataKey="ts"
          tickFormatter={formatTime}
          tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'var(--color-border)' }}
          tickLine={false}
          minTickGap={40}
        />
        <YAxis
          tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
          width={56}
          tickFormatter={(v: number) => formatNumber(v)}
        />
        <Tooltip
          contentStyle={{
            background: 'var(--color-card)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
            fontSize: 12,
          }}
          labelStyle={{ color: 'var(--color-muted-foreground)', fontFamily: 'var(--font-mono)' }}
          labelFormatter={(v) => formatTime(String(v))}
          formatter={(value, name) => [formatNumber(Number(value)), String(name)]}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, color: 'var(--color-muted-foreground)' }}
          formatter={(value: string) => (value === 'allowed' ? t('dashboard.legendAllowed') : t('dashboard.legendBlocked'))}
        />
        <Area
          type="monotone"
          dataKey="allowed"
          stackId="1"
          stroke="url(#allowedStroke)"
          strokeWidth={2.5}
          fill="url(#allowedFill)"
        />
        <Area
          type="monotone"
          dataKey="blocked"
          stackId="1"
          stroke="url(#blockedStroke)"
          strokeWidth={2.5}
          fill="url(#blockedFill)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
