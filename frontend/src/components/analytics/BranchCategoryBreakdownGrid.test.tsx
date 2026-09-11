import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BranchCategoryBreakdownGrid } from '@/components/analytics/BranchCategoryBreakdownGrid'
import type { BranchCategoryBreakdownResponse } from '@/types/api'

const DATA: BranchCategoryBreakdownResponse = {
  series: [
    {
      branch: 'hq',
      categories: [
        { category: 'video_streaming', request_count: 100, total_bytes: 90_000, bytes_received: 3_000 },
        { category: 'work_tools', request_count: 40, total_bytes: 1_000, bytes_received: 0 },
      ],
    },
    {
      branch: 'warehouse',
      categories: [],
    },
  ],
}

describe('BranchCategoryBreakdownGrid', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(<BranchCategoryBreakdownGrid loading />)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows the empty state with no series', () => {
    render(<BranchCategoryBreakdownGrid data={{ series: [] }} />)
    expect(screen.getByText('No branch traffic in this range.')).toBeInTheDocument()
  })

  it('renders one tile per branch, with a "nothing" state for an empty one', () => {
    render(<BranchCategoryBreakdownGrid data={DATA} />)
    expect(screen.getByText('hq')).toBeInTheDocument()
    expect(screen.getByText('warehouse')).toBeInTheDocument()
    expect(screen.getByText('No traffic in this range.')).toBeInTheDocument()
  })

  it('shows each category label and its byte share', () => {
    render(<BranchCategoryBreakdownGrid data={DATA} />)
    expect(screen.getByText('Video streaming')).toBeInTheDocument()
    expect(screen.getByText('Work tools')).toBeInTheDocument()
    expect(screen.getByText('87.9 KB')).toBeInTheDocument()
  })

  it('shows uploaded bytes alongside downloaded, when present', () => {
    render(<BranchCategoryBreakdownGrid data={DATA} />)
    // video_streaming has bytes_received=3_000 -> shown with an upload arrow
    expect(screen.getByText('↑2.9 KB')).toBeInTheDocument()
    // work_tools has bytes_received=0 -> no upload annotation for that row
    expect(screen.queryByText('↑0 B')).not.toBeInTheDocument()
  })
})
