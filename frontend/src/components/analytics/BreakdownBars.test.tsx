import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BreakdownBars } from '@/components/analytics/BreakdownBars'
import type { NamedCount } from '@/types/api'

const ITEMS: NamedCount[] = [
  { label: 'TCP_MISS', request_count: 800, total_bytes: 40000, pct: 80 },
  { label: 'TCP_DENIED', request_count: 200, total_bytes: 1000, pct: 20 },
]

describe('BreakdownBars', () => {
  it('renders one row per item with its count and percentage', () => {
    render(<BreakdownBars items={ITEMS} />)
    expect(screen.getByText('TCP_MISS')).toBeInTheDocument()
    expect(screen.getByText('800')).toBeInTheDocument()
    expect(screen.getByText('80.0%')).toBeInTheDocument()
  })

  it('respects the row limit', () => {
    render(<BreakdownBars items={ITEMS} limit={1} />)
    expect(screen.getByText('TCP_MISS')).toBeInTheDocument()
    expect(screen.queryByText('TCP_DENIED')).not.toBeInTheDocument()
  })

  it('emphasizes a matched label', () => {
    render(<BreakdownBars items={ITEMS} emphasize={(l) => l.includes('DENIED')} />)
    expect(screen.getByText('TCP_DENIED')).toHaveClass('text-destructive')
  })

  it('shows an empty state', () => {
    render(<BreakdownBars items={[]} />)
    expect(screen.getByText('No data for this range.')).toBeInTheDocument()
  })
})
