import {
  Area,
  AreaChart,
  Brush,
  CartesianGrid,
  Legend,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  type DotItemDotProps,
  type MouseHandlerDataParam,
} from 'recharts'
import { formatNumber, formatTime } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { AnomalyEvent, TimeseriesPoint } from '@/types/api'

interface TrafficChartProps {
  points: TimeseriesPoint[]
  loading?: boolean
  /** Called with a point's raw `bucket_ts` when the chart is clicked on (or
   * near) that point. Omit to keep the chart non-interactive. The caller
   * knows the bucket width it requested (see DashboardPage), so turning
   * this into a [start, end) window is left to it rather than threaded
   * through here. */
  onSelectBucket?: (bucketTs: string) => void
  /** Recent anomalies (see useInsights) to mark on the chart -- not
   * range-scoped by the API, so only the ones that land within the plotted
   * points are actually shown (see anomalyMarkers below). */
  anomalies?: AnomalyEvent[]
  /** Whether the live WebSocket feed is currently connected -- draws a
   * pulsing dot on the most recent point when true, same "live" signal
   * DashboardPage already threads into every other query on this page. */
  live?: boolean
  /** Id of an anomaly (from `anomalies`) to draw with emphasis -- e.g. after
   * clicking its row in InsightsPanel. No effect if that anomaly didn't end
   * up producing a marker (out of range, or lost a same-bucket severity
   * tiebreak -- see anomalyMarkers). */
  highlightedAnomalyId?: string | null
}

const SUCCESS = '#22c55e'
const WARNING = '#f5a524'
const WARNING_DEEP = '#f97316'

const SEVERITY_RANK: Record<AnomalyEvent['severity'], number> = { low: 0, medium: 1, high: 2, critical: 3 }

/** Anomalies aren't generated at exact bucket boundaries, and the X axis is
 * category-typed (one tick per plotted bucket) rather than a continuous
 * time scale, so a marker can only ever land on one of the ticks that
 * already exists -- this snaps each anomaly to its nearest plotted bucket,
 * drops any anomaly further from every bucket than half the chart's own
 * span (i.e. clearly outside the visible window), and keeps only the most
 * severe anomaly per bucket so two anomalies a minute apart don't draw two
 * indistinguishable overlapping lines. */
function anomalyMarkers(
  points: TimeseriesPoint[],
  anomalies: AnomalyEvent[],
): { ts: string; id: string; title: string; severity: AnomalyEvent['severity'] }[] {
  const first = points[0]
  if (!first || anomalies.length === 0) return []
  const second = points[1]
  const bucketMs = second ? new Date(second.bucket_ts).getTime() - new Date(first.bucket_ts).getTime() : Infinity
  const maxSnapMs = Math.max(bucketMs, 60_000) * 2

  const byTs = new Map<string, { ts: string; id: string; title: string; severity: AnomalyEvent['severity'] }>()
  for (const anomaly of anomalies) {
    const anomalyMs = new Date(anomaly.generated_at).getTime()
    if (Number.isNaN(anomalyMs)) continue

    let nearest = first
    let nearestDelta = Math.abs(new Date(nearest.bucket_ts).getTime() - anomalyMs)
    for (const point of points) {
      const delta = Math.abs(new Date(point.bucket_ts).getTime() - anomalyMs)
      if (delta < nearestDelta) {
        nearest = point
        nearestDelta = delta
      }
    }
    if (nearestDelta > maxSnapMs) continue

    const existing = byTs.get(nearest.bucket_ts)
    if (!existing || SEVERITY_RANK[anomaly.severity] > SEVERITY_RANK[existing.severity]) {
      byTs.set(nearest.bucket_ts, {
        ts: nearest.bucket_ts,
        id: anomaly.id,
        title: anomaly.title,
        severity: anomaly.severity,
      })
    }
  }
  return Array.from(byTs.values())
}

export function TrafficChart({
  points,
  loading,
  onSelectBucket,
  anomalies = [],
  live,
  highlightedAnomalyId,
}: TrafficChartProps) {
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
    total: p.total_requests,
  }))
  const markers = anomalyMarkers(points, anomalies)
  const lastIndex = data.length - 1

  function handleClick(state: MouseHandlerDataParam) {
    if (!onSelectBucket) return
    // activeLabel is the clicked point's XAxis dataKey value ("ts" below) --
    // undefined when the click lands outside the plotted area, not on/near
    // a point, so there's nothing to drill into.
    if (typeof state.activeLabel === 'string') onSelectBucket(state.activeLabel)
  }

  // Marks only the most recent point, and only while actually live -- a
  // plain dot everywhere would just be visual noise on a line this dense.
  function renderLiveDot({ cx, cy, index }: DotItemDotProps) {
    if (index !== lastIndex || typeof cx !== 'number' || typeof cy !== 'number') return <g />
    return (
      <g>
        <circle cx={cx} cy={cy} r={3.5} fill={SUCCESS} stroke="var(--color-card)" strokeWidth={1.5} />
        <circle cx={cx} cy={cy} r={3.5} fill={SUCCESS} opacity={0.55}>
          <animate attributeName="r" values="3.5;10" dur="1.6s" repeatCount="indefinite" />
          <animate attributeName="opacity" values="0.55;0" dur="1.6s" repeatCount="indefinite" />
        </circle>
      </g>
    )
  }

  return (
    <ResponsiveContainer width="100%" height={320}>
      <AreaChart
        data={data}
        margin={{ top: 8, right: 8, left: 0, bottom: 0 }}
        onClick={onSelectBucket ? handleClick : undefined}
        className={onSelectBucket ? 'cursor-pointer' : undefined}
      >
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
          formatter={(value, name, item) => {
            const num = Number(value)
            const total = Number((item.payload as { total?: number }).total ?? 0)
            const pct = total > 0 ? Math.round((num / total) * 100) : 0
            const label = name === 'allowed' ? t('dashboard.legendAllowed') : t('dashboard.legendBlocked')
            return [`${formatNumber(num)} (${pct}%)`, label]
          }}
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
          dot={live ? renderLiveDot : false}
          isAnimationActive
          animationDuration={400}
          animationEasing="ease-out"
        />
        <Area
          type="monotone"
          dataKey="blocked"
          stackId="1"
          stroke="url(#blockedStroke)"
          strokeWidth={2.5}
          fill="url(#blockedFill)"
          isAnimationActive
          animationDuration={400}
          animationEasing="ease-out"
        />
        {markers.map((marker) => {
          const color = marker.severity === 'critical' ? 'var(--color-destructive)' : 'var(--color-warning)'
          const isHighlighted = marker.id === highlightedAnomalyId
          return (
            <ReferenceLine
              key={marker.ts}
              x={marker.ts}
              stroke={color}
              strokeWidth={isHighlighted ? 2.5 : 1}
              strokeDasharray="4 4"
              strokeOpacity={isHighlighted ? 1 : 0.8}
              label={{
                value: '⚠',
                position: 'top',
                fontSize: isHighlighted ? 16 : 12,
                fill: color,
              }}
            >
              <title>{marker.title}</title>
            </ReferenceLine>
          )
        })}
        <Brush
          dataKey="ts"
          height={22}
          travellerWidth={8}
          tickFormatter={formatTime}
          stroke="var(--color-border)"
          fill="var(--color-secondary)"
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
