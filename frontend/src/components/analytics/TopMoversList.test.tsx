import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { TopMoversList } from '@/components/analytics/TopMoversList'
import type { CategoryMover } from '@/types/api'

describe('TopMoversList', () => {
  it('renders the empty state with no movers', () => {
    render(<TopMoversList movers={[]} />)
    expect(screen.getByText('No change to compare yet.')).toBeInTheDocument()
  })

  it('labels a category with no previous data as "new"', () => {
    const movers: CategoryMover[] = [
      { category: 'video_streaming', current_bytes: 5_000_000, previous_bytes: 0, pct_change: null },
    ]
    render(<TopMoversList movers={movers} />)
    expect(screen.getByText('Video streaming')).toBeInTheDocument()
    expect(screen.getByText('new')).toBeInTheDocument()
  })

  it('shows a rounded percentage for a real change', () => {
    const movers: CategoryMover[] = [
      { category: 'news', current_bytes: 1200, previous_bytes: 1000, pct_change: 20 },
    ]
    render(<TopMoversList movers={movers} />)
    expect(screen.getByText('20%')).toBeInTheDocument()
  })
})
