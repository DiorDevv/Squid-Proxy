import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { CATEGORY_COLORS, CATEGORY_LABEL_KEYS } from '@/lib/categories'
import { formatBytes, formatNumber } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { CategoryTrendResponse } from '@/types/api'

interface CategoryTrendChartProps {
  data?: CategoryTrendResponse
  loading?: boolean
}

function formatBucket(iso: string, granularity: 'hour' | 'day'): string {
  const date = new Date(iso)
  if (granularity === 'day') {
    return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit' }).format(date)
  }
  return new Intl.DateTimeFormat('en-US', { month: 'short', day: '2-digit', hour: '2-digit', hour12: false }).format(
    date,
  )
}

export function CategoryTrendChart({ data, loading }: CategoryTrendChartProps) {
  const { t } = useTranslation()

  if (loading) {
    return <div className="h-80 w-full animate-pulse rounded-md bg-muted" />
  }

  if (!data || data.points.length === 0) {
    return (
      <div className="flex h-80 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.trend.empty')}
      </div>
    )
  }

  const formatValue = data.metric === 'bytes' ? formatBytes : formatNumber
  const rows = data.points.map((point) => {
    const row: Record<string, number | string> = { ts: point.bucket_ts }
    for (const category of data.categories) {
      row[category] = point.values[category] ?? 0
    }
    return row
  })

  return (
    <ResponsiveContainer width="100%" height={340}>
      <AreaChart data={rows} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
        <XAxis
          dataKey="ts"
          tickFormatter={(value: string) => formatBucket(value, data.granularity)}
          tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'var(--color-border)' }}
          tickLine={false}
          minTickGap={44}
        />
        <YAxis
          tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
          width={64}
          tickFormatter={(value: number) => formatValue(value)}
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
            formatValue(Number(value)),
            t(CATEGORY_LABEL_KEYS[name as keyof typeof CATEGORY_LABEL_KEYS] ?? 'category.other'),
          ]}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, color: 'var(--color-muted-foreground)' }}
          formatter={(value: string) =>
            t(CATEGORY_LABEL_KEYS[value as keyof typeof CATEGORY_LABEL_KEYS] ?? 'category.other')
          }
        />
        {data.categories.map((category) => (
          <Area
            key={category}
            type="monotone"
            dataKey={category}
            stackId="1"
            stroke={CATEGORY_COLORS[category]}
            fill={CATEGORY_COLORS[category]}
            fillOpacity={0.35}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        ))}
      </AreaChart>
    </ResponsiveContainer>
  )
}
