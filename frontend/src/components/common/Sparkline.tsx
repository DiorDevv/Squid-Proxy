import { Area, AreaChart, ResponsiveContainer } from 'recharts'

interface SparklineProps {
  /** Raw series, oldest first -- downsampled by the caller if it's long
   * (see DashboardPage's downsample helper); this component just plots
   * whatever it's given. */
  values: number[]
  /** Short, unique-per-instance key (e.g. "total", "blocked") used to
   * namespace this sparkline's SVG gradient id -- multiple sparklines on
   * one page would otherwise collide on a shared `id`. */
  id: string
  color: string
}

/** Minimal, axis-less trend line for a summary card -- no tooltip/grid/axes,
 * animation off (these redraw on every live poll; a decorative strip this
 * small isn't worth animating that often). Renders nothing below 2 points,
 * since a single point has no trend to show. */
export function Sparkline({ values, id, color }: SparklineProps) {
  if (values.length < 2) return null
  const data = values.map((value, index) => ({ index, value }))
  const gradientId = `sparkline-fill-${id}`

  return (
    <ResponsiveContainer width="100%" height={32}>
      <AreaChart data={data} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
        <defs>
          <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={color} stopOpacity={0.35} />
            <stop offset="100%" stopColor={color} stopOpacity={0} />
          </linearGradient>
        </defs>
        <Area
          type="monotone"
          dataKey="value"
          stroke={color}
          strokeWidth={1.5}
          fill={`url(#${gradientId})`}
          isAnimationActive={false}
        />
      </AreaChart>
    </ResponsiveContainer>
  )
}
