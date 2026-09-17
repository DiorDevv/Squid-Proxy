import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BranchComparisonChart } from '@/components/analytics/BranchComparisonChart'
import type { BranchBreakdownRow } from '@/types/api'

const ROWS: BranchBreakdownRow[] = [
  {
    branch: 'hq',
    total_requests: 9600,
    blocked_requests: 702,
    allowed_requests: 8898,
    total_bytes: 8_640_000,
    blocked_ratio: 0.073,
    active_client_count: 6,
    requests_pct_change: null,
  },
]

describe('BranchComparisonChart', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(<BranchComparisonChart rows={[]} loading />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows the empty state with no rows', () => {
    render(<BranchComparisonChart rows={[]} />)
    expect(screen.getByText('No branch traffic in this range.')).toBeInTheDocument()
  })

  it('renders a chart container for real rows', () => {
    const { container } = render(<BranchComparisonChart rows={ROWS} />)
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument()
  })
})
