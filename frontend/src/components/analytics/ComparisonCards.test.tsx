import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { ComparisonCards } from '@/components/analytics/ComparisonCards'
import type { MetricDelta } from '@/types/api'

const METRICS: MetricDelta[] = [
  { metric: 'total_requests', current: 19140, previous: 0, pct_change: null },
  { metric: 'blocked_requests', current: 1413, previous: 1000, pct_change: 41.3 },
  { metric: 'allowed_requests', current: 17727, previous: 0, pct_change: null },
  { metric: 'total_bytes', current: 17_000_000, previous: 0, pct_change: null },
  { metric: 'active_clients', current: 12, previous: 0, pct_change: null },
  { metric: 'blocked_ratio', current: 0.07, previous: null, pct_change: null },
  { metric: 'cache_hit_ratio', current: 0.4, previous: null, pct_change: null },
]

describe('ComparisonCards', () => {
  it('renders the five volume headline labels', () => {
    render(<ComparisonCards metrics={METRICS} loading={false} />)
    for (const label of ['Total requests', 'Blocked', 'Allowed', 'Data transferred', 'Active clients']) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('does not duplicate the operational ratios (they live in the health strip)', () => {
    render(<ComparisonCards metrics={METRICS} loading={false} />)
    expect(screen.queryByText('Blocked share')).not.toBeInTheDocument()
    expect(screen.queryByText('Cache hit rate')).not.toBeInTheDocument()
  })

  it('renders loading skeletons instead of values', () => {
    const { container } = render(<ComparisonCards metrics={[]} loading />)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })
})
