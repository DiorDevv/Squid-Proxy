import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatNumber } from '@/lib/format'
import type { TrendGranularity } from '@/types/api'

interface Row {
  bucket_ts: string
  values: Record<string, number>
}

interface StackedAreaOverTimeProps {
  rows: Row[]
  labels: string[]
  granularity: TrendGranularity
  colorFor: (label: string) => string
  labelFor?: (label: string) => string
  height?: number
  loading?: boolean
  emptyText: string
}

function formatBucket(iso: string, granularity: TrendGranularity): string {
  const date = new Date(iso)
  if (granularity === 'day') {
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit' }).format(date)
  }
  return new Intl.DateTimeFormat('en-US', {
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    hour12: false,
  }).format(date)
}

export function StackedAreaOverTime({
  rows,
  labels,
  granularity,
  colorFor,
  labelFor = (l) => l,
  height = 300,
  loading,
  emptyText,
}: StackedAreaOverTimeProps) {
  if (loading) {
    return <div className="w-full animate-pulse rounded-md bg-muted" style={{ height }} />
  }
  if (rows.length === 0 || labels.length === 0) {
    return (
      <div className="flex items-center justify-center text-sm text-muted-foreground" style={{ height }}>
        {emptyText}
      </div>
    )
  }

  const data = rows.map((row) => {
    const flat: Record<string, number | string> = { ts: row.bucket_ts }
    for (const label of labels) flat[label] = row.values[label] ?? 0
    return flat
  })

  return (
    <ResponsiveContainer width="100%" height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
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
          labelFormatter={(v) => formatBucket(String(v), granularity)}
          formatter={(value, name) => [formatNumber(Number(value)), labelFor(String(name))]}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, color: 'var(--color-muted-foreground)' }}
          formatter={(value: string) => labelFor(value)}
        />
        {labels.map((label) => (
          <Area
            key={label}
            type="monotone"
            dataKey={label}
            stackId="1"
            stroke={colorFor(label)}
            fill={colorFor(label)}
            fillOpacity={0.32}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}
