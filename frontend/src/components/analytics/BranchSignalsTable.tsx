import { useState } from 'react'
import { ArrowDown, ArrowUp } from 'lucide-react'
import { cn } from '@/lib/utils'
import { formatNumber } from '@/lib/format'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { BranchSignalRow } from '@/types/api'

type SortKey =
  | 'branch'
  | 'total_requests'
  | 'blocked_ratio'
  | 'sensitive_traffic_share'
  | 'anomaly_count'
  | 'quota_breach_count'
  | 'uncategorized_domain_count'

const COLUMNS: { key: SortKey; labelKey: TranslationKey; numeric: boolean }[] = [
  { key: 'branch', labelKey: 'analytics.branches.colBranch', numeric: false },
  { key: 'total_requests', labelKey: 'analytics.branches.colRequests', numeric: true },
  { key: 'blocked_ratio', labelKey: 'analytics.branches.colBlockedPct', numeric: true },
  { key: 'sensitive_traffic_share', labelKey: 'analytics.branches.colSensitivePct', numeric: true },
  { key: 'anomaly_count', labelKey: 'analytics.branches.colAnomalies', numeric: true },
  { key: 'quota_breach_count', labelKey: 'analytics.branches.colQuota', numeric: true },
  { key: 'uncategorized_domain_count', labelKey: 'analytics.branches.colUncategorized', numeric: true },
]

const pct = (v: number) => `${(v * 100).toFixed(1)}%`

/** Raw per-branch attention signals, side by side -- no composite score or
 * band (see the backend note on BranchSignalRow). Sortable by any column so
 * the operator picks the lens; a cell is tinted when its value is the
 * worst in that column and non-zero. */
export function BranchSignalsTable({
  rows,
  loading,
}: {
  rows: BranchSignalRow[]
  loading?: boolean
}) {
  const { t } = useTranslation()
  const [sort, setSort] = useState<{ key: SortKey; desc: boolean }>({
    key: 'blocked_ratio',
    desc: true,
  })

  if (loading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <div key={i} className="h-10 w-full animate-pulse rounded bg-muted" />
        ))}
      </div>
    )
  }
  if (rows.length === 0) {
    return (
      <div className="flex h-24 items-center justify-center text-sm text-muted-foreground">
        {t('analytics.branches.empty')}
      </div>
    )
  }

  const worst: Partial<Record<SortKey, number>> = {}
  for (const col of COLUMNS) {
    if (col.numeric && col.key !== 'total_requests') {
      worst[col.key] = Math.max(...rows.map((r) => r[col.key] as number))
    }
  }

  const sorted = [...rows].sort((a, b) => {
    const av = a[sort.key]
    const bv = b[sort.key]
    const cmp = typeof av === 'string' ? av.localeCompare(bv as string) : (av as number) - (bv as number)
    return sort.desc ? -cmp : cmp
  })

  const toggle = (key: SortKey) =>
    setSort((s) => (s.key === key ? { key, desc: !s.desc } : { key, desc: key !== 'branch' }))

  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            {COLUMNS.map((col) => (
              <TableHead
                key={col.key}
                className={cn('cursor-pointer select-none whitespace-nowrap', col.numeric && 'text-right')}
                onClick={() => toggle(col.key)}
              >
                <span className={cn('inline-flex items-center gap-1', col.numeric && 'flex-row-reverse')}>
                  {t(col.labelKey)}
                  {sort.key === col.key &&
                    (sort.desc ? (
                      <ArrowDown className="h-3 w-3" aria-hidden="true" />
                    ) : (
                      <ArrowUp className="h-3 w-3" aria-hidden="true" />
                    ))}
                </span>
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {sorted.map((row) => (
            <TableRow key={row.branch}>
              <TableCell className="font-medium">{row.branch}</TableCell>
              <TableCell className="font-data text-right text-muted-foreground">
                {formatNumber(row.total_requests)}
              </TableCell>
              <NumCell value={pct(row.blocked_ratio)} worst={row.blocked_ratio > 0 && row.blocked_ratio === worst.blocked_ratio} />
              <NumCell
                value={pct(row.sensitive_traffic_share)}
                worst={row.sensitive_traffic_share > 0 && row.sensitive_traffic_share === worst.sensitive_traffic_share}
              />
              <NumCell value={formatNumber(row.anomaly_count)} worst={row.anomaly_count > 0 && row.anomaly_count === worst.anomaly_count} />
              <NumCell value={formatNumber(row.quota_breach_count)} worst={row.quota_breach_count > 0 && row.quota_breach_count === worst.quota_breach_count} />
              <NumCell
                value={formatNumber(row.uncategorized_domain_count)}
                worst={row.uncategorized_domain_count > 0 && row.uncategorized_domain_count === worst.uncategorized_domain_count}
              />
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

function NumCell({ value, worst }: { value: string; worst: boolean }) {
  return (
    <TableCell className={cn('font-data text-right', worst ? 'font-semibold text-warning' : 'text-muted-foreground')}>
      {value}
    </TableCell>
  )
}
