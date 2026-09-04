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
  it('renders every headline metric label', () => {
    render(<ComparisonCards metrics={METRICS} loading={false} />)
    for (const label of [
      'Total requests',
      'Blocked',
      'Allowed',
      'Data transferred',
      'Active clients',
      'Blocked share',
      'Cache hit rate',
    ]) {
      expect(screen.getByText(label)).toBeInTheDocument()
    }
  })

  it('scales the ratio metrics to a percent for display', () => {
    render(<ComparisonCards metrics={METRICS} loading={false} />)
    // blocked_ratio 0.07 -> "7.0%", cache_hit_ratio 0.4 -> "40.0%"
    expect(screen.getByText('7.0%')).toBeInTheDocument()
    expect(screen.getByText('40.0%')).toBeInTheDocument()
  })

  it('renders loading skeletons instead of values', () => {
    const { container } = render(<ComparisonCards metrics={[]} loading />)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })
})
