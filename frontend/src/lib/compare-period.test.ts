import { describe, expect, it } from 'vitest'
import { getPercentChange, getPreviousPeriodParams } from '@/lib/compare-period'

describe('getPreviousPeriodParams', () => {
  it('returns an equal-duration window immediately preceding the current one', () => {
    const result = getPreviousPeriodParams('2026-01-02T00:00:00.000Z', '2026-01-03T00:00:00.000Z', null)
    expect(result).toEqual({
      from_ts: '2026-01-01T00:00:00.000Z',
      to_ts: '2026-01-02T00:00:00.000Z',
    })
  })

  it('carries the branch filter through when one is selected', () => {
    const result = getPreviousPeriodParams('2026-01-02T00:00:00.000Z', '2026-01-03T00:00:00.000Z', 'hq')
    expect(result).toEqual({
      from_ts: '2026-01-01T00:00:00.000Z',
      to_ts: '2026-01-02T00:00:00.000Z',
      branch: 'hq',
    })
  })

  it('preserves an odd (non-24h) duration exactly, e.g. a 1h range', () => {
    const result = getPreviousPeriodParams('2026-01-02T10:00:00.000Z', '2026-01-02T11:00:00.000Z', null)
    expect(result).toEqual({
      from_ts: '2026-01-02T09:00:00.000Z',
      to_ts: '2026-01-02T10:00:00.000Z',
    })
  })
})

describe('getPercentChange', () => {
  it('computes a positive percentage increase', () => {
    expect(getPercentChange(150, 100)).toBe(50)
  })

  it('computes a negative percentage decrease', () => {
    expect(getPercentChange(50, 100)).toBe(-50)
  })

  it('returns null when there is no previous-period value yet', () => {
    expect(getPercentChange(100, undefined)).toBeNull()
  })

  it('returns null when the previous value was zero, avoiding a division by zero', () => {
    expect(getPercentChange(100, 0)).toBeNull()
  })
})
