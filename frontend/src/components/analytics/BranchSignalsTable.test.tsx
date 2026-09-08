import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { BranchSignalsTable } from '@/components/analytics/BranchSignalsTable'
import type { BranchSignalRow } from '@/types/api'

const ROWS: BranchSignalRow[] = [
  {
    branch: 'quiet',
    total_requests: 1000,
    blocked_requests: 10,
    blocked_ratio: 0.01,
    sensitive_traffic_share: 0,
    anomaly_count: 0,
    quota_breach_count: 0,
    uncategorized_domain_count: 0,
  },
  {
    branch: 'noisy',
    total_requests: 5000,
    blocked_requests: 2000,
    blocked_ratio: 0.4,
    sensitive_traffic_share: 0.12,
    anomaly_count: 3,
    quota_breach_count: 1,
    uncategorized_domain_count: 2,
  },
]

/** Branch names in body-row order (header row dropped). */
function branchOrder(): string[] {
  return screen
    .getAllByRole('row')
    .slice(1)
    .map((r) => r.querySelector('td')?.textContent ?? '')
}

describe('BranchSignalsTable', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(<BranchSignalsTable rows={[]} loading />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows the empty state with no rows', () => {
    render(<BranchSignalsTable rows={[]} />)
    expect(screen.getByText('No branch traffic in this range.')).toBeInTheDocument()
  })

  it('defaults to worst blocked ratio first and has no score/band', () => {
    render(<BranchSignalsTable rows={ROWS} />)
    expect(branchOrder()).toEqual(['noisy', 'quiet'])
    expect(screen.queryByText(/risk/i)).not.toBeInTheDocument()
    expect(screen.getByText('40.0%')).toBeInTheDocument()
  })

  it('re-sorts ascending by branch name when that header is clicked', async () => {
    render(<BranchSignalsTable rows={ROWS} />)
    await userEvent.click(screen.getByText('Branch'))
    expect(branchOrder()).toEqual(['noisy', 'quiet'])
    await userEvent.click(screen.getByText('Branch'))
    expect(branchOrder()).toEqual(['quiet', 'noisy'])
  })
})
