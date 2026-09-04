import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { WatchlistPanel } from '@/components/settings/WatchlistPanel'
import * as apiClient from '@/lib/api-client'
import type { WatchlistEntry } from '@/types/api'

const ENTRY: WatchlistEntry = {
  id: 'w1',
  target_type: 'domain',
  value: 'bet365.com',
  note: 'suspicious',
  branch: '',
  active: true,
  created_at: '2026-09-04T00:00:00Z',
  last_seen_at: '2026-09-04T10:00:00Z',
  last_alerted_at: null,
}

function renderPanel() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <WatchlistPanel />
    </QueryClientProvider>,
  )
}

describe('WatchlistPanel', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('lists watched entries with their type and last-active time', async () => {
    vi.spyOn(apiClient, 'apiFetch').mockImplementation(async (path: string) => {
      if (path === '/api/watchlist') return [ENTRY] as unknown
      if (path === '/api/branches') return { items: [] } as unknown
      throw new Error(`unexpected ${path}`)
    })

    renderPanel()
    await waitFor(() => expect(screen.getByText('bet365.com')).toBeInTheDocument())
    expect(screen.getByText('suspicious')).toBeInTheDocument()
    // the "Watching" toggle reflects the active entry
    expect(screen.getByRole('button', { name: 'On' })).toBeInTheDocument()
  })

  it('shows the empty state when nothing is watched', async () => {
    vi.spyOn(apiClient, 'apiFetch').mockImplementation(async (path: string) => {
      if (path === '/api/watchlist') return [] as unknown
      if (path === '/api/branches') return { items: [] } as unknown
      throw new Error(`unexpected ${path}`)
    })

    renderPanel()
    await waitFor(() => expect(screen.getByText('Nothing is being watched.')).toBeInTheDocument())
  })
})
