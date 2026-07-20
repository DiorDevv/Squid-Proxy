import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { useFiltersStore, useRangeSearchParams } from '@/lib/filters-store'

const INITIAL_STATE = useFiltersStore.getState()

describe('useRangeSearchParams', () => {
  beforeEach(() => {
    useFiltersStore.setState(INITIAL_STATE, true)
  })

  afterEach(() => {
    useFiltersStore.setState(INITIAL_STATE, true)
  })

  it('resolves to just { range } with no branch selected', () => {
    const { result } = renderHook(() => useRangeSearchParams())
    expect(result.current).toEqual({ range: '24h' })
  })

  it('adds branch once one is selected, without disturbing the range preset', () => {
    const { result } = renderHook(() => useRangeSearchParams())

    act(() => {
      useFiltersStore.getState().setBranch('hq')
    })

    expect(result.current).toEqual({ range: '24h', branch: 'hq' })
  })

  it('clears branch from the resolved params when reset to "all branches"', () => {
    const { result } = renderHook(() => useRangeSearchParams())

    act(() => {
      useFiltersStore.getState().setBranch('hq')
    })
    act(() => {
      useFiltersStore.getState().setBranch(null)
    })

    expect(result.current).toEqual({ range: '24h' })
  })

  it('carries branch through a custom range window too', () => {
    const { result } = renderHook(() => useRangeSearchParams())

    act(() => {
      useFiltersStore.getState().setCustomRange('2026-01-01T00:00:00.000Z', '2026-01-02T00:00:00.000Z')
      useFiltersStore.getState().setBranch('branch-office')
    })

    expect(result.current).toEqual({
      from_ts: '2026-01-01T00:00:00.000Z',
      to_ts: '2026-01-02T00:00:00.000Z',
      branch: 'branch-office',
    })
  })
})
