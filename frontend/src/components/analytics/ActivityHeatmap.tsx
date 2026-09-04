import { formatNumber } from '@/lib/format'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { ActivityHeatmapResponse } from '@/types/api'

const WEEKDAY_KEYS: TranslationKey[] = [
  'analytics.heatmap.mon',
  'analytics.heatmap.tue',
  'analytics.heatmap.wed',
  'analytics.heatmap.thu',
  'analytics.heatmap.fri',
  'analytics.heatmap.sat',
  'analytics.heatmap.sun',
]

const HOURS = Array.from({ length: 24 }, (_, hour) => hour)

interface ActivityHeatmapProps {
  data?: ActivityHeatmapResponse
  loading?: boolean
}

/** "UTC" or "UTC+05:00" / "UTC-04:30" for a minutes-east-of-UTC offset.
 * A missing/non-finite value (e.g. an older backend that doesn't send the
 * field) falls back to plain "UTC" rather than rendering "UTC-NaN:NaN". */
function formatTzLabel(offsetMinutes: number | undefined): string {
  if (!Number.isFinite(offsetMinutes) || offsetMinutes === 0) return 'UTC'
  const minutes = offsetMinutes as number
  const sign = minutes > 0 ? '+' : '-'
  const abs = Math.abs(minutes)
  const hh = String(Math.floor(abs / 60)).padStart(2, '0')
  const mm = String(abs % 60).padStart(2, '0')
  return `UTC${sign}${hh}:${mm}`
}

/** Hour (x) x weekday (y) grid, colored by request volume. Buckets are
 * split by weekday/hour in the viewer's local timezone (the backend
 * applies the offset -- see useActivityHeatmap); the exact zone used is
 * shown in the panel note. */
export function ActivityHeatmap({ data, loading }: ActivityHeatmapProps) {
  const { t } = useTranslation()

  if (loading) {
    return <div className="h-64 w-full animate-pulse rounded-md bg-muted" />
  }

  if (!data || data.cells.length === 0) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.heatmap.empty')}
      </div>
    )
  }

  const grid = new Map<string, number>()
  for (const cell of data.cells) grid.set(`${cell.weekday}-${cell.hour}`, cell.value)
  const max = data.max_value || 1
  const baseColor = data.blocked_only ? '239, 68, 68' : '59, 130, 246' // red-500 / blue-500
  const tzLabel = formatTzLabel(data.tz_offset_minutes)

  return (
    <div className="flex flex-col gap-2 overflow-x-auto">
      <div className="min-w-[560px]">
        <div className="grid grid-cols-[40px_repeat(24,1fr)] gap-0.5">
          <div />
          {HOURS.map((hour) => (
            <div key={hour} className="text-center text-[9px] text-muted-foreground">
              {hour % 3 === 0 ? hour : ''}
            </div>
          ))}

          {WEEKDAY_KEYS.map((weekdayKey, weekday) => (
            <div key={weekday} className="contents">
              <div className="flex items-center pr-1 text-[10px] text-muted-foreground">{t(weekdayKey)}</div>
              {HOURS.map((hour) => {
                const value = grid.get(`${weekday}-${hour}`) ?? 0
                const intensity = value === 0 ? 0 : 0.12 + 0.88 * (value / max)
                return (
                  <div
                    key={hour}
                    className="aspect-square rounded-[2px] border border-border/40"
                    style={{ backgroundColor: `rgba(${baseColor}, ${intensity})` }}
                    title={`${t(weekdayKey)} ${String(hour).padStart(2, '0')}:00 ${tzLabel} — ${formatNumber(value)}`}
                  />
                )
              })}
            </div>
          ))}
        </div>
      </div>
      <p className="text-[11px] text-muted-foreground">{t('analytics.heatmap.tzNote', { tz: tzLabel })}</p>
    </div>
  )
}
