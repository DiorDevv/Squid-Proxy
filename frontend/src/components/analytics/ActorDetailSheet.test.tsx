import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ActorDetailSheet } from '@/components/analytics/ActorDetailSheet'
import { TooltipProvider } from '@/components/ui/tooltip'
import { useFiltersStore } from '@/lib/filters-store'
import * as apiClient from '@/lib/api-client'
import type { ActorDetailResponse, ActorRow, WatchlistEntry } from '@/types/api'

const navigateMock = vi.fn()
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

function renderWithRouter(ui: React.ReactElement) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={client}>
      <TooltipProvider>
        <MemoryRouter>{ui}</MemoryRouter>
      </TooltipProvider>
    </QueryClientProvider>,
  )
}

const DETAIL: ActorDetailResponse = {
  actor: '10.0.0.5',
  is_user: false,
  first_seen: null,
  last_seen: null,
  request_count: 300,
  blocked_count: 12,
  total_bytes: 9000,
  bytes_received: 1200,
  blocked_bytes: 500,
  blocked_bytes_received: 80,
  request_count_pct_change: 0.25,
  blocked_count_pct_change: null,
  total_bytes_pct_change: -0.1,
  bytes_received_pct_change: 0.5,
  blocked_bytes_pct_change: null,
  hourly: Array<number>(24).fill(0),
  top_domains: [
    { domain: 'cnn.com', category: 'news', request_count: 150, blocked_count: 0, total_bytes: 4000, bytes_received: 700 },
  ],
  denied_domains: [],
  categories: [
    {
      category: 'news',
      request_count: 200,
      total_bytes: 6000,
      bytes_received: 900,
      domains: [
        { domain: 'cnn.com', category: 'news', request_count: 150, blocked_count: 0, total_bytes: 4000, bytes_received: 700 },
        { domain: 'bbc.com', category: 'news', request_count: 50, blocked_count: 2, total_bytes: 2000, bytes_received: 200 },
      ],
    },
    {
      category: 'social_media',
      request_count: 100,
      total_bytes: 3000,
      bytes_received: 100,
      domains: [
        { domain: 'x.com', category: 'social_media', request_count: 100, blocked_count: 0, total_bytes: 3000, bytes_received: 100 },
      ],
    },
  ],
}

vi.mock('@/hooks/useAnalytics', () => ({
  useActorDetail: () => ({ data: DETAIL, isLoading: false }),
}))

// Mutable so individual tests can flip role without a fresh vi.mock per test.
let mockRole = 'auditor'
vi.mock('@/lib/auth-store', () => ({
  useAuthStore: (selector: (state: { role: string }) => unknown) => selector({ role: mockRole }),
}))

const ACTOR: ActorRow = {
  actor: '10.0.0.5',
  is_user: false,
  request_count: 300,
  blocked_count: 12,
  blocked_ratio: 0.04,
  total_bytes: 9000,
  bytes_received: 1200,
  top_category: 'news',
}

describe('ActorDetailSheet', () => {
  it('nests each category over the domains that resolved to it', () => {
    renderWithRouter(<ActorDetailSheet actor={ACTOR} rangeParams={{}} onOpenChange={() => {}} />)

    const newsDetails = screen.getByText('News').closest('details')
    expect(newsDetails).not.toBeNull()
    expect(within(newsDetails as HTMLElement).getByText('cnn.com')).toBeInTheDocument()
    expect(within(newsDetails as HTMLElement).getByText('bbc.com')).toBeInTheDocument()
    // bbc.com had 2 blocked requests -> shows the blocked marker
    expect(within(newsDetails as HTMLElement).getByText('2 ✕')).toBeInTheDocument()

    // a domain from another category is not under News
    expect(within(newsDetails as HTMLElement).queryByText('x.com')).toBeNull()
  })

  it('shows blocked bytes as its own figure, not folded into Downloaded/Uploaded', () => {
    renderWithRouter(<ActorDetailSheet actor={ACTOR} rangeParams={{}} onOpenChange={() => {}} />)

    expect(screen.getByText('Blocked traffic')).toBeInTheDocument()
    // 500 + 80 = 580 -- the combined blocked_bytes/blocked_bytes_received,
    // separate from the 9000/1200 Downloaded/Uploaded figures above.
    expect(screen.getByText('580 B')).toBeInTheDocument()
  })

  it('shows top domains as their own section', () => {
    renderWithRouter(<ActorDetailSheet actor={ACTOR} rangeParams={{}} onOpenChange={() => {}} />)

    expect(screen.getByText('Top domains')).toBeInTheDocument()
  })

  it('hands the actor off to the Events page and navigates there on "View all events"', async () => {
    const user = userEvent.setup()
    renderWithRouter(<ActorDetailSheet actor={ACTOR} rangeParams={{}} onOpenChange={() => {}} />)

    await user.click(screen.getByRole('button', { name: 'View all events' }))

    expect(useFiltersStore.getState().pendingEventsSearch).toBe(ACTOR.actor)
    expect(navigateMock).toHaveBeenCalledWith('/events')
  })
})

describe('ActorDetailSheet watchlist toggle', () => {
  afterEach(() => {
    mockRole = 'auditor'
    vi.restoreAllMocks()
  })

  it('does not show a watch action for non-admin roles', async () => {
    vi.spyOn(apiClient, 'apiFetch').mockResolvedValue([] as unknown as WatchlistEntry[])
    renderWithRouter(<ActorDetailSheet actor={ACTOR} rangeParams={{}} onOpenChange={() => {}} />)

    expect(screen.queryByRole('button', { name: 'Watch' })).toBeNull()
    expect(screen.queryByRole('button', { name: 'Watching' })).toBeNull()
  })

  it('lets an admin add the actor to the watchlist from the sheet', async () => {
    mockRole = 'admin'
    const user = userEvent.setup()
    let entries: WatchlistEntry[] = []
    vi.spyOn(apiClient, 'apiFetch').mockImplementation(async (path: string, options?: { method?: string }) => {
      if (path === '/api/watchlist' && (!options?.method || options.method === 'GET')) {
        return entries as unknown
      }
      if (path === '/api/watchlist' && options?.method === 'POST') {
        const entry: WatchlistEntry = {
          id: 'new1',
          target_type: 'client_ip',
          value: ACTOR.actor,
          note: null,
          branch: '',
          active: true,
          created_at: '2026-09-17T00:00:00Z',
          last_seen_at: null,
          last_alerted_at: null,
        }
        entries = [entry]
        return entry as unknown
      }
      throw new Error(`unexpected request: ${path} ${options?.method ?? 'GET'}`)
    })

    renderWithRouter(<ActorDetailSheet actor={ACTOR} rangeParams={{}} onOpenChange={() => {}} />)

    const watchButton = await screen.findByRole('button', { name: 'Watch' })
    await user.click(watchButton)

    expect(await screen.findByRole('button', { name: 'Watching' })).toBeInTheDocument()
  })

  it('shows Watching for an actor already on the watchlist', async () => {
    mockRole = 'admin'
    const entry: WatchlistEntry = {
      id: 'w1',
      target_type: 'client_ip',
      value: ACTOR.actor,
      note: null,
      branch: '',
      active: true,
      created_at: '2026-09-17T00:00:00Z',
      last_seen_at: null,
      last_alerted_at: null,
    }
    vi.spyOn(apiClient, 'apiFetch').mockResolvedValue([entry] as unknown as WatchlistEntry[])

    renderWithRouter(<ActorDetailSheet actor={ACTOR} rangeParams={{}} onOpenChange={() => {}} />)

    expect(await screen.findByRole('button', { name: 'Watching' })).toBeInTheDocument()
  })
})
