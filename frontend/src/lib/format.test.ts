import { describe, expect, it } from 'vitest'
import { formatBytes, formatDuration, formatNumber, formatRelativeTime } from '@/lib/format'

describe('formatBytes', () => {
  it('formats zero as 0 B', () => {
    expect(formatBytes(0)).toBe('0 B')
  })

  it('formats bytes below 1024 with no decimal', () => {
    expect(formatBytes(512)).toBe('512 B')
  })

  it('formats kilobytes with one decimal', () => {
    expect(formatBytes(2048)).toBe('2.0 KB')
  })

  it('formats megabytes', () => {
    expect(formatBytes(5 * 1024 * 1024)).toBe('5.0 MB')
  })

  // Regression test: formatBytes previously called Math.log on negative
  // input, producing NaN and rendering the literal string "undefined B".
  it('guards against negative input', () => {
    expect(formatBytes(-100)).toBe('0 B')
  })

  it('guards against NaN input', () => {
    expect(formatBytes(NaN)).toBe('0 B')
  })

  it('guards against non-finite input', () => {
    expect(formatBytes(Infinity)).toBe('0 B')
  })
})

describe('formatNumber', () => {
  it('adds thousands separators', () => {
    expect(formatNumber(1234567)).toBe('1,234,567')
  })

  it('formats zero', () => {
    expect(formatNumber(0)).toBe('0')
  })
})

describe('formatRelativeTime', () => {
  it('returns "never" for null', () => {
    expect(formatRelativeTime(null)).toBe('never')
  })

  it('returns "just now" for very recent timestamps', () => {
    expect(formatRelativeTime(new Date().toISOString())).toBe('just now')
  })

  it('returns seconds ago for recent-but-not-just-now timestamps', () => {
    const tenSecondsAgo = new Date(Date.now() - 10_000).toISOString()
    expect(formatRelativeTime(tenSecondsAgo)).toBe('10s ago')
  })

  it('returns minutes ago', () => {
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60_000).toISOString()
    expect(formatRelativeTime(fiveMinutesAgo)).toBe('5m ago')
  })

  it('returns hours ago', () => {
    const threeHoursAgo = new Date(Date.now() - 3 * 60 * 60_000).toISOString()
    expect(formatRelativeTime(threeHoursAgo)).toBe('3h ago')
  })

  it('returns days ago', () => {
    const twoDaysAgo = new Date(Date.now() - 2 * 24 * 60 * 60_000).toISOString()
    expect(formatRelativeTime(twoDaysAgo)).toBe('2d ago')
  })
})

describe('formatDuration', () => {
  it('formats zero and negative input as 0m', () => {
    expect(formatDuration(0)).toBe('0m')
    expect(formatDuration(-5)).toBe('0m')
  })

  it('formats seconds under a minute', () => {
    expect(formatDuration(45)).toBe('45s')
  })

  it('formats minutes', () => {
    expect(formatDuration(5 * 60)).toBe('5m')
  })

  it('formats hours with remaining minutes', () => {
    expect(formatDuration(2 * 3600 + 15 * 60)).toBe('2h 15m')
  })

  it('formats whole hours without a minutes suffix', () => {
    expect(formatDuration(3 * 3600)).toBe('3h')
  })
})
