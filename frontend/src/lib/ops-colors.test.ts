import { describe, expect, it } from 'vitest'
import { durationBandColor, resultCodeColor, statusClassColor } from '@/lib/ops-colors'

describe('resultCodeColor', () => {
  it('reads Squid result tags semantically', () => {
    expect(resultCodeColor('TCP_HIT')).toBe('#22c55e')
    expect(resultCodeColor('TCP_MEM_HIT')).toBe('#22c55e')
    expect(resultCodeColor('TCP_MISS')).toBe('#f59e0b')
    expect(resultCodeColor('TCP_DENIED')).toBe('#ef4444')
    expect(resultCodeColor('TCP_TUNNEL')).toBe('#a855f7')
    expect(resultCodeColor('NONE')).toBe('#64748b')
  })
})

describe('statusClassColor', () => {
  it('maps HTTP status classes to a green/blue/amber/red scale', () => {
    expect(statusClassColor('2xx')).toBe('#22c55e')
    expect(statusClassColor('3xx')).toBe('#3b82f6')
    expect(statusClassColor('4xx')).toBe('#f59e0b')
    expect(statusClassColor('5xx')).toBe('#ef4444')
  })
})

describe('durationBandColor', () => {
  it('goes green (fast) to dark red (slow)', () => {
    expect(durationBandColor('<100ms')).toBe('#22c55e')
    expect(durationBandColor('>=10s')).toBe('#b91c1c')
    expect(durationBandColor('unknown')).toBe('#64748b')
  })
})
