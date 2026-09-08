import { render, screen, within } from '@testing-library/react'
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

describe('BranchSignalsTable', () => {
  it('shows a skeleton while loading', () => {
    const { container } = render(<BranchSignalsTable rows={[]} loading />)
    expect(container.querySelector('.animate-pulse')).toBeInTheDocument()
  })

  it('shows the empty state with no rows', () => {
    render(<BranchSignalsTable rows={[]} />)
    expect(screen.getByText('No branch traffic in this range.')).toBeInTheDocument()
  })

  it('defaults to worst blocked ratio first and has no score/band column', () => {
    render(<BranchSignalsTable rows={ROWS} />)
    const bodyRows = screen.getAllByRole('row').slice(1) // drop header
    expect(within(bodyRows[0]).getByText('noisy')).toBeInTheDocument()
    expect(within(bodyRows[1]).getByText('quiet')).toBeInTheDocument()
    expect(screen.queryByText(/risk/i)).not.toBeInTheDocument()
    expect(screen.getByText('40.0%')).toBeInTheDocument()
  })

  it('re-sorts when a column header is clicked', async () => {
    render(<BranchSignalsTable rows={ROWS} />)
    await userEvent.click(screen.getByText('Branch'))
    const bodyRows = screen.getAllByRole('row').slice(1)
    // ascending by branch name: noisy before quiet
    expect(within(bodyRows[0]).getByText('noisy')).toBeInTheDocument()
  })
})
