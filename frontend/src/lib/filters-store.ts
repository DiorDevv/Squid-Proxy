import { create } from 'zustand'
import type { RangeParam } from '@/types/api'

interface FiltersState {
  range: RangeParam
  /** 'custom' means customFrom/customTo (ISO datetimes) are the active
   * window instead of the `range` preset -- see useRangeSearchParams. */
  mode: 'preset' | 'custom'
  customFrom: string | null
  customTo: string | null
  setRange: (range: RangeParam) => void
  setCustomRange: (from: string, to: string) => void
}

export const useFiltersStore = create<FiltersState>((set) => ({
  range: '24h',
  mode: 'preset',
  customFrom: null,
  customTo: null,
  setRange: (range) => set({ range, mode: 'preset' }),
  setCustomRange: (from, to) => set({ customFrom: from, customTo: to, mode: 'custom' }),
}))

/** Resolves the current filter selection into the query params every
 * range-based endpoint understands (see backend app/schemas/common.py:
 * resolve_range) -- either `{ range }` or a custom `{ from_ts, to_ts }`
 * pair, so data hooks don't each need to know about custom-range mode. */
export function useRangeSearchParams(): Record<string, string> {
  const { mode, range, customFrom, customTo } = useFiltersStore()
  if (mode === 'custom' && customFrom && customTo) {
    return { from_ts: customFrom, to_ts: customTo }
  }
  return { range }
}
