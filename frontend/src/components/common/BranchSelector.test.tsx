import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { BranchSelector } from '@/components/common/BranchSelector'
import { apiFetch } from '@/lib/api-client'
import { useFiltersStore } from '@/lib/filters-store'
import type { BranchesResponse } from '@/types/api'

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client')
  return { ...actual, apiFetch: vi.fn() }
})

const INITIAL_STATE = useFiltersStore.getState()

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

describe('BranchSelector', () => {
  beforeEach(() => {
    vi.mocked(apiFetch).mockReset()
    useFiltersStore.setState(INITIAL_STATE, true)
  })

  it('renders nothing for a single-branch deployment', async () => {
    const single: BranchesResponse = { items: [{ slug: 'default', label: 'Default' }] }
    vi.mocked(apiFetch).mockResolvedValueOnce(single)

    const { container } = render(<BranchSelector />, { wrapper })

    await waitFor(() => expect(apiFetch).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('lists every configured branch plus an "all branches" option', async () => {
    const multi: BranchesResponse = {
      items: [
        { slug: 'hq', label: 'HQ' },
        { slug: 'branch-office', label: 'Branch Office' },
      ],
    }
    vi.mocked(apiFetch).mockResolvedValueOnce(multi)

    render(<BranchSelector />, { wrapper })

    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByRole('combobox'))

    expect(await screen.findByRole('option', { name: 'All branches' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'HQ' })).toBeInTheDocument()
    expect(screen.getByRole('option', { name: 'Branch Office' })).toBeInTheDocument()
  })

  it('updates the shared filters store when a branch is picked', async () => {
    const multi: BranchesResponse = {
      items: [
        { slug: 'hq', label: 'HQ' },
        { slug: 'branch-office', label: 'Branch Office' },
      ],
    }
    vi.mocked(apiFetch).mockResolvedValueOnce(multi)

    render(<BranchSelector />, { wrapper })
    await waitFor(() => expect(screen.getByRole('combobox')).toBeInTheDocument())

    const user = userEvent.setup()
    await user.click(screen.getByRole('combobox'))
    await user.click(await screen.findByRole('option', { name: 'HQ' }))

    expect(useFiltersStore.getState().branch).toBe('hq')
  })
})
