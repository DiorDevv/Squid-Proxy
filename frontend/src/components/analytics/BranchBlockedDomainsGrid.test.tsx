import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { BranchBlockedDomainsGrid } from '@/components/analytics/BranchBlockedDomainsGrid'
import type { BranchBlockedDomainsResponse } from '@/types/api'

const DATA: BranchBlockedDomainsResponse = {
  since: '2026-09-11T00:00:00Z',
  until: '2026-09-11T01:00:00Z',
  series: [
    {
      branch: 'hq',
      domains: [{ domain: 'gambling-x.com', blocked_count: 80 }],
    },
    {
      branch: 'warehouse',
      domains: [],
    },
  ],
}

const navigateMock = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

function renderWithRouter(ui: React.ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>)
}

describe('BranchBlockedDomainsGrid', () => {
  it('shows a skeleton while loading', () => {
    const { container } = renderWithRouter(<BranchBlockedDomainsGrid loading />)
    expect(container.querySelectorAll('.animate-pulse').length).toBeGreaterThan(0)
  })

  it('shows the empty state with no series', () => {
    renderWithRouter(<BranchBlockedDomainsGrid data={{ since: DATA.since, until: DATA.until, series: [] }} />)
    expect(screen.getByText('No branch traffic in this range.')).toBeInTheDocument()
  })

  it('renders one tile per branch, with a "nothing blocked" state for an empty one', () => {
    renderWithRouter(<BranchBlockedDomainsGrid data={DATA} />)
    expect(screen.getByText('hq')).toBeInTheDocument()
    expect(screen.getByText('warehouse')).toBeInTheDocument()
    expect(screen.getByText('gambling-x.com')).toBeInTheDocument()
    expect(screen.getByText('Nothing blocked in this range.')).toBeInTheDocument()
  })

  it('navigates to the domain detail page on click', async () => {
    const user = userEvent.setup()
    renderWithRouter(<BranchBlockedDomainsGrid data={DATA} />)
    await user.click(screen.getByText('gambling-x.com'))
    expect(navigateMock).toHaveBeenCalledWith('/domains/gambling-x.com')
  })
})
