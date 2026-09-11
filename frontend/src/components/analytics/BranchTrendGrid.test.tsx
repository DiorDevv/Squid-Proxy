import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BranchTrendGrid } from '@/components/analytics/BranchTrendGrid'
import type { BranchTrendResponse } from '@/types/api'

const DATA: BranchTrendResponse = {
  granularity: 'hour',
  series: [
    {
      branch: 'hq',
      points: [
        { bucket_ts: '2026-09-11T10:00:00Z', total_requests: 120, blocked_requests: 20, allowed_requests: 100 },
        { bucket_ts: '2026-09-11T11:00:00Z', total_requests: 80, blocked_requests: 0, allowed_requests: 80 },
      ],
    },
    {
      branch: 'warehouse',
      points: [],
    },
  ],
}

describe('BranchTrendGrid', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(<BranchTrendGrid loading />)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows the empty state with no series', () => {
    render(<BranchTrendGrid data={{ granularity: 'hour', series: [] }} />)
    expect(screen.getByText('No branch traffic in this range.')).toBeInTheDocument()
  })

  it('renders one tile per branch, including a silent one', () => {
    render(<BranchTrendGrid data={DATA} />)
    expect(screen.getByText('hq')).toBeInTheDocument()
    expect(screen.getByText('warehouse')).toBeInTheDocument()
    // the silent branch gets its own "no traffic" tile, not a chart
    expect(screen.getByText('No traffic in this range.')).toBeInTheDocument()
  })

  it('renders a chart for a branch with points', () => {
    const { container } = render(<BranchTrendGrid data={DATA} />)
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument()
  })

  it('shows the branch total and blocked count', () => {
    render(<BranchTrendGrid data={DATA} />)
    expect(screen.getByText('200')).toBeInTheDocument() // 120 + 80 total_requests
    expect(screen.getByText(/20 blocked/)).toBeInTheDocument()
  })
})
