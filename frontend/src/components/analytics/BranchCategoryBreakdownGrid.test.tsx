import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BranchCategoryBreakdownGrid } from '@/components/analytics/BranchCategoryBreakdownGrid'
import type { BranchCategoryBreakdownResponse } from '@/types/api'

const DATA: BranchCategoryBreakdownResponse = {
  series: [
    {
      branch: 'hq',
      categories: [
        { category: 'video_streaming', request_count: 100, total_bytes: 90_000 },
        { category: 'work_tools', request_count: 40, total_bytes: 1_000 },
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
})
