import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { formatNumber } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { BranchBreakdownRow } from '@/types/api'

const ALLOWED = '#22c55e'
const BLOCKED = '#ef4444'

interface BranchComparisonChartProps {
  rows: BranchBreakdownRow[]
  loading?: boolean
}

/** Allowed vs. blocked request volume per branch, side by side -- the
 * "which branch is carrying the load, and where is traffic getting
 * blocked" view. */
export function BranchComparisonChart({ rows, loading }: BranchComparisonChartProps) {
  const { t } = useTranslation()

  if (loading) {
    return <div className="h-72 w-full animate-pulse rounded-md bg-muted" />
  }
  if (rows.length === 0) {
    return (
      <div className="flex h-72 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.branches.empty')}
      </div>
    )
  }

  const data = rows.map((row) => ({
    branch: row.branch,
    allowed: row.allowed_requests,
    blocked: row.blocked_requests,
  }))

  return (
    <ResponsiveContainer width="100%" height={300}>
      <BarChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
        <XAxis
          dataKey="branch"
          tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={{ stroke: 'var(--color-border)' }}
          tickLine={false}
        />
        <YAxis
          tick={{ fill: 'var(--color-muted-foreground)', fontSize: 11, fontFamily: 'var(--font-mono)' }}
          axisLine={false}
          tickLine={false}
          width={56}
          tickFormatter={(value: number) => formatNumber(value)}
        />
        <Tooltip
          cursor={{ fill: 'var(--color-secondary)', opacity: 0.4 }}
          contentStyle={{
            background: 'var(--color-card)',
            border: '1px solid var(--color-border)',
            borderRadius: 'var(--radius-md)',
            fontSize: 12,
          }}
          formatter={(value, name) => [
            formatNumber(Number(value)),
            name === 'allowed' ? t('analytics.metric.allowed') : t('analytics.metric.blocked'),
          ]}
        />
        <Legend
          wrapperStyle={{ fontSize: 12, color: 'var(--color-muted-foreground)' }}
          formatter={(value: string) =>
            value === 'allowed' ? t('analytics.metric.allowed') : t('analytics.metric.blocked')
          }
        />
        <Bar dataKey="allowed" stackId="a" fill={ALLOWED} radius={[0, 0, 0, 0]} isAnimationActive={false} />
        <Bar dataKey="blocked" stackId="a" fill={BLOCKED} radius={[3, 3, 0, 0]} isAnimationActive={false} />
      </BarChart>
    </ResponsiveContainer>
  )
}
