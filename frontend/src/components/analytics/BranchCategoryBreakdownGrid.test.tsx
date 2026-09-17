import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BranchCategoryBreakdownGrid } from '@/components/analytics/BranchCategoryBreakdownGrid'
import type { BranchCategoryBreakdownResponse, DomainCategoryLabel } from '@/types/api'

// 7 categories -- deliberately more than the old top-6 cap, to prove every
// one of them renders now, not just a sample.
const SEVEN_CATEGORIES: DomainCategoryLabel[] = [
  'video_streaming',
  'work_tools',
  'social_media',
  'music_streaming',
  'gaming',
  'shopping',
  'news',
]

const DATA: BranchCategoryBreakdownResponse = {
  series: [
    {
      branch: 'hq',
      categories: SEVEN_CATEGORIES.map((category, i) => ({
        category,
        request_count: 100 - i,
        total_bytes: 90_000 - i * 1_000,
        bytes_received: i === 0 ? 3_000 : 0,
      })),
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

  it('renders every category, not just a top-N sample', () => {
    render(<BranchCategoryBreakdownGrid data={DATA} />)
    expect(screen.getByText('Video streaming')).toBeInTheDocument()
    expect(screen.getByText('Work tools')).toBeInTheDocument()
    expect(screen.getByText('Social media')).toBeInTheDocument()
    expect(screen.getByText('Music streaming')).toBeInTheDocument()
    expect(screen.getByText('Gaming')).toBeInTheDocument()
    expect(screen.getByText('Shopping')).toBeInTheDocument()
    expect(screen.getByText('News')).toBeInTheDocument()
  })

  it('shows a table with requests, downloaded, and uploaded columns', () => {
    render(<BranchCategoryBreakdownGrid data={DATA} />)
    expect(screen.getByText('Category')).toBeInTheDocument()
    expect(screen.getByText('Total requests')).toBeInTheDocument()
    expect(screen.getByText('Downloaded')).toBeInTheDocument()
    expect(screen.getByText('Uploaded')).toBeInTheDocument()

    expect(screen.getByText('100')).toBeInTheDocument() // video_streaming request_count
    expect(screen.getByText('87.9 KB')).toBeInTheDocument() // video_streaming total_bytes
    expect(screen.getByText('2.9 KB')).toBeInTheDocument() // video_streaming bytes_received
  })

  it('shows an em dash for uploaded when there is none, not "0 B"', () => {
    render(<BranchCategoryBreakdownGrid data={DATA} />)
    // work_tools (index 1) has bytes_received=0
    const rows = screen.getAllByText('—')
    expect(rows.length).toBeGreaterThan(0)
    expect(screen.queryByText('0 B')).not.toBeInTheDocument()
  })
})
