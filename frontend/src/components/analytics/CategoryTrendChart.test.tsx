import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { CategoryTrendChart } from '@/components/analytics/CategoryTrendChart'
import type { CategoryTrendResponse } from '@/types/api'

describe('CategoryTrendChart', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(<CategoryTrendChart loading />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows the empty state when there are no points', () => {
    const data: CategoryTrendResponse = { granularity: 'hour', metric: 'bytes', categories: [], points: [] }
    render(<CategoryTrendChart data={data} />)
    expect(screen.getByText('No data for this range.')).toBeInTheDocument()
  })

  it('renders a chart container when there is data', () => {
    const data: CategoryTrendResponse = {
      granularity: 'hour',
      metric: 'bytes',
      categories: ['video_streaming', 'gambling'],
      points: [
        { bucket_ts: '2026-09-04T02:00:00Z', values: { video_streaming: 1200000, gambling: 19200 } },
        { bucket_ts: '2026-09-04T03:00:00Z', values: { video_streaming: 3000000, gambling: 48000 } },
      ],
    }
    const { container } = render(<CategoryTrendChart data={data} />)
    expect(container.querySelector('.recharts-responsive-container')).toBeInTheDocument()
  })
})
