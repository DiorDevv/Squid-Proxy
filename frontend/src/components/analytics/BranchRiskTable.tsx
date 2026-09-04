import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatNumber } from '@/lib/format'
import {
  RISK_BAND_LABEL_KEYS,
  RISK_BAND_STYLES,
  RISK_SIGNAL_COLORS,
  RISK_SIGNAL_LABEL_KEYS,
  formatRiskRawValue,
} from '@/lib/risk'
import { useTranslation } from '@/i18n'
import type { BranchRiskRow } from '@/types/api'

interface BranchRiskTableProps {
  rows: BranchRiskRow[]
  loading?: boolean
}

/** One row per branch, highest composite risk first (ordering comes from
 * the API). The score is a weighted blend of five signals -- click a row
 * to see each signal's raw value and its point contribution. */
export function BranchRiskTable({ rows, loading }: BranchRiskTableProps) {
  const { t } = useTranslation()
  const [expanded, setExpanded] = useState<string | null>(null)

  if (loading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-16 w-full animate-pulse rounded-md bg-muted" />
        ))}
      </div>
    )
  }

  if (rows.length === 0) {
    return (
      <div className="flex h-32 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.branches.empty')}
      </div>
    )
  }

  return (
    <ul className="flex flex-col divide-y divide-border">
      {rows.map((row) => {
        const style = RISK_BAND_STYLES[row.band]
        const isOpen = expanded === row.branch
        return (
          <li key={row.branch}>
            <button
              type="button"
              onClick={() => setExpanded(isOpen ? null : row.branch)}
              className="flex w-full items-center gap-3 py-3 text-left transition-colors duration-150 hover:bg-secondary/40"
              aria-expanded={isOpen}
            >
              {isOpen ? (
                <ChevronDown className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              ) : (
                <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground" aria-hidden="true" />
              )}

              <div className="flex w-28 shrink-0 flex-col">
                <span className="truncate text-sm font-medium text-foreground">{row.branch}</span>
                <span
                  className={cn(
                    'mt-0.5 w-fit rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase',
                    style.bg,
                    style.text,
                  )}
                >
                  {t(RISK_BAND_LABEL_KEYS[row.band])}
                </span>
              </div>

              <div className={cn('font-data w-14 shrink-0 text-2xl font-semibold', style.text)}>
                {Math.round(row.score)}
              </div>

              {/* Stacked signal-contribution bar: segment widths are each
                  signal's points out of the full 100. */}
              <div className="flex h-2.5 min-w-0 flex-1 overflow-hidden rounded-full bg-muted">
                {row.signals.map((signal) => (
                  <div
                    key={signal.key}
                    style={{ width: `${signal.score}%`, backgroundColor: RISK_SIGNAL_COLORS[signal.key] }}
                    title={`${t(RISK_SIGNAL_LABEL_KEYS[signal.key])}: ${signal.score.toFixed(1)}`}
                  />
                ))}
              </div>

              <div className="font-data hidden w-40 shrink-0 flex-col text-right text-xs text-muted-foreground sm:flex">
                <span>{t('analytics.branches.requestsShort', { count: formatNumber(row.total_requests) })}</span>
                <span>
                  {t('analytics.branches.anomaliesShort', { count: formatNumber(row.anomaly_count) })}
                </span>
              </div>
            </button>

            {isOpen && (
              <div className="flex flex-col gap-1.5 pb-3 pl-7 pr-2">
                {row.signals.map((signal) => (
                  <div key={signal.key} className="flex items-center gap-3 text-xs">
                    <span
                      className="h-2 w-2 shrink-0 rounded-full"
                      style={{ backgroundColor: RISK_SIGNAL_COLORS[signal.key] }}
                      aria-hidden="true"
                    />
                    <span className="min-w-0 flex-1 truncate text-foreground">
                      {t(RISK_SIGNAL_LABEL_KEYS[signal.key])}
                    </span>
                    <span className="font-data text-muted-foreground">
                      {formatRiskRawValue(signal.key, signal.raw_value)}
                    </span>
                    <span className="font-data w-24 text-right text-muted-foreground">
                      {t('analytics.risk.contribution', { points: signal.score.toFixed(1) })}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </li>
        )
      })}
    </ul>
  )
}
