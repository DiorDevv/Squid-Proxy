import { create } from 'zustand'
import type { RangeParam } from '@/types/api'

interface FiltersState {
  range: RangeParam
  /** 'custom' means customFrom/customTo (ISO datetimes) are the active
   * window instead of the `range` preset -- see useRangeSearchParams. */
  mode: 'preset' | 'custom'
  customFrom: string | null
  customTo: string | null
  /** null means "all branches" -- see useRangeSearchParams. */
  branch: string | null
  setRange: (range: RangeParam) => void
  setCustomRange: (from: string, to: string) => void
  setBranch: (branch: string | null) => void
}

export const useFiltersStore = create<FiltersState>((set) => ({
  range: '24h',
  mode: 'preset',
  customFrom: null,
  customTo: null,
  branch: null,
  setRange: (range) => set({ range, mode: 'preset' }),
  setCustomRange: (from, to) => set({ customFrom: from, customTo: to, mode: 'custom' }),
  setBranch: (branch) => set({ branch }),
}))

/** Resolves the current filter selection into the query params every
 * range-based endpoint understands (see backend app/schemas/common.py:
 * resolve_range) -- either `{ range }` or a custom `{ from_ts, to_ts }`
 * pair, plus `branch` when one is selected, so data hooks don't each need
 * to know about custom-range mode or the branch filter individually --
 * every hook that already spreads rangeParams into its searchParams picks
 * both up for free. */
export function useRangeSearchParams(): Record<string, string> {
  const { mode, range, customFrom, customTo, branch } = useFiltersStore()
  if (mode === 'custom' && customFrom && customTo) {
    return branch ? { from_ts: customFrom, to_ts: customTo, branch } : { from_ts: customFrom, to_ts: customTo }
  }
  return branch ? { range, branch } : { range }
}
