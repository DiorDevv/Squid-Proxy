import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ActorLeaderboardResponse, ActorRow } from '@/types/api'

const leaderboardCalls: unknown[][] = []
const downloadActorList = vi.fn().mockResolvedValue(undefined)
let role = 'admin'

function rows(count: number, start: number): ActorRow[] {
  return Array.from({ length: count }, (_, i) => ({
    actor: `10.0.0.${start + i}`,
    is_user: false,
    request_count: 1000 - start - i,
    blocked_count: 0,
    blocked_ratio: 0,
    total_bytes: 0,
    bytes_received: 0,
    top_category: null,
  }))
}

vi.mock('@/hooks/useAnalytics', () => ({
  useActorLeaderboard: (...args: unknown[]) => {
    leaderboardCalls.push(args)
    const offset = (args[5] as number) ?? 0
    const data: ActorLeaderboardResponse = {
      actor_kind: 'mixed',
      rows: rows(50, offset),
      unattributed_requests: 0,
      total: 120,
      user_count: 20,
      ip_count: 100,
    }
    return { data, isLoading: false, isError: false, refetch: vi.fn() }
  },
  useNewEntities: () => ({ data: undefined, isLoading: false }),
  useActorDetail: () => ({ data: undefined, isLoading: false }),
}))
vi.mock('@/hooks/useWatchlist', () => ({
  useWatchlist: () => ({ data: [] }),
  useCreateWatchlistEntry: () => ({ mutate: vi.fn() }),
  useDeleteWatchlistEntry: () => ({ mutate: vi.fn() }),
  isWatchlistConflict: () => false,
}))
vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  downloadActorList: (...args: unknown[]) => downloadActorList(...args),
}))
vi.mock('@/lib/auth-store', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/auth-store')>()
  return {
    ...actual,
    useAuthStore: (selector: (s: { role: string }) => unknown) => selector({ role }),
  }
})

const { default: AnalyticsWhoPage } = await import('@/pages/analytics/AnalyticsWhoPage')

const renderPage = () =>
  render(
    <MemoryRouter>
      <AnalyticsWhoPage />
    </MemoryRouter>,
  )

describe('AnalyticsWhoPage', () => {
  beforeEach(() => {
    leaderboardCalls.length = 0
    downloadActorList.mockClear()
    role = 'admin'
  })

  it('shows the totals and per-kind counts, and pages through the whole list', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(screen.getByText('Total: 120 (20 users, 100 IPs)')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /Users only/ })).toHaveTextContent('20')
    expect(screen.getByText(/^Page 1 of 3 . 120 total$/)).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Next page' }))
    expect(leaderboardCalls.at(-1)?.[5]).toBe(50)
    // ranks continue from the previous page
    expect(screen.getByText('51')).toBeInTheDocument()

    // switching the filter starts again from page 1, asking for that kind
    await user.click(screen.getByRole('tab', { name: /IPs only/ }))
    expect(leaderboardCalls.at(-1)?.slice(5)).toEqual([0, 'ip'])
  })

  it('exports the whole list with the current filter, for admins only', async () => {
    const user = userEvent.setup()
    const { unmount } = renderPage()
    await user.click(screen.getByRole('tab', { name: /Users only/ }))
    await user.click(screen.getByRole('button', { name: /Excel/ }))
    expect(downloadActorList).toHaveBeenCalledWith('xlsx', expect.objectContaining({ kind: 'user', sort: 'requests' }))
    unmount()

    role = 'viewer'
    renderPage()
    expect(screen.queryByRole('button', { name: /Excel/ })).not.toBeInTheDocument()
  })
})
