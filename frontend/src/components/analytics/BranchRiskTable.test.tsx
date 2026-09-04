import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { BranchRiskTable } from '@/components/analytics/BranchRiskTable'
import type { BranchRiskRow } from '@/types/api'

const ROW: BranchRiskRow = {
  branch: 'warehouse',
  score: 42.5,
  band: 'medium',
  total_requests: 9540,
  blocked_requests: 711,
  anomaly_count: 2,
  signals: [
    { key: 'blocked_ratio', raw_value: 0.074, score: 5.6, weight: 0.3 },
    { key: 'sensitive_traffic', raw_value: 0.6, score: 15, weight: 0.25 },
    { key: 'anomalies', raw_value: 6, score: 3.75, weight: 0.25 },
    { key: 'quota_breaches', raw_value: 0, score: 0, weight: 0.1 },
    { key: 'uncategorized_domains', raw_value: 0, score: 0, weight: 0.1 },
  ],
}

describe('BranchRiskTable', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(<BranchRiskTable rows={[]} loading />)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('renders the branch, rounded score and band label', () => {
    render(<BranchRiskTable rows={[ROW]} />)
    expect(screen.getByText('warehouse')).toBeInTheDocument()
    expect(screen.getByText('43')).toBeInTheDocument() // Math.round(42.5)
    expect(screen.getByText('Medium')).toBeInTheDocument()
  })

  it('reveals the per-signal breakdown when a row is clicked', async () => {
    const user = userEvent.setup()
    render(<BranchRiskTable rows={[ROW]} />)

    expect(screen.queryByText('Sensitive-category traffic')).not.toBeInTheDocument()
    await user.click(screen.getByRole('button', { expanded: false }))

    expect(screen.getByText('Sensitive-category traffic')).toBeInTheDocument()
    expect(screen.getByText('60.0%')).toBeInTheDocument() // raw_value of the sensitive signal
    expect(screen.getByText('+15.0 pts')).toBeInTheDocument() // its contribution
  })
})
