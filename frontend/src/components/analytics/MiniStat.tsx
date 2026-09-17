import { cn } from '@/lib/utils'

interface MiniStatProps {
  label: string
  value: string
  tone?: 'default' | 'good' | 'warn' | 'bad'
  hint?: string
}

const TONE: Record<NonNullable<MiniStatProps['tone']>, string> = {
  default: 'text-foreground',
  good: 'text-success',
  warn: 'text-amber-500',
  bad: 'text-destructive',
}

/** Compact single-number tile for the Squid-ops views (hit ratio, denied
 * %, p95, 403/407/5xx counts). Lighter than dashboard/SummaryCard -- no
 * animation, sparkline or delta. */
export function MiniStat({ label, value, tone = 'default', hint }: MiniStatProps) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-border bg-card p-3">
      <span className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className={cn('font-data text-xl font-semibold', TONE[tone])}>{value}</span>
      {hint && <span className="text-[11px] text-muted-foreground">{hint}</span>}
    </div>
  )
}
