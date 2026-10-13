import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BlockGroupsResponse, BlockSummary } from '@/types/api'

const eventsCalls: Record<string, unknown>[] = []
const groupCalls: Record<string, unknown>[] = []
const summaryCalls: Record<string, unknown>[] = []
const downloadBlockedGroups = vi.fn().mockResolvedValue(undefined)
let role = 'admin'

const summary: BlockSummary = {
  domains: 37,
  denied: 72231,
  auth: 9000,
  clients: 1309,
  users: 214,
  branches: ['filial', 'main'],
  proxies: ['172.25.42.77'],
  series: [],
  available_proxies: ['172.25.42.24', '172.25.42.77'],
}

const groups: BlockGroupsResponse = {
  group: 'domain',
  items: [
    {
      key: 'crl.usertrust.com',
      denied_count: 25616,
      auth_count: 331,
      client_count: 806,
      user_count: 12,
      domain_count: 1,
      branches: ['filial', 'main'],
      proxies: ['172.25.42.77'],
      first_seen: '2026-10-06T11:00:00Z',
      last_seen: '2026-10-13T11:00:00Z',
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
}

vi.mock('@/hooks/useEvents', () => ({
  useEvents: (params: Record<string, unknown>) => {
    eventsCalls.push(params)
    return { data: { items: [], total: 0, limit: 50, offset: 0 }, isLoading: false, isError: false }
  },
}))
vi.mock('@/hooks/useBlockedAnalysis', () => ({
  useBlockSummary: (params: Record<string, unknown>) => {
    summaryCalls.push(params)
    return { data: summary, isFetching: false, isError: false }
  },
  useBlockGroups: (params: Record<string, unknown>) => {
    groupCalls.push(params)
    return { data: params.enabled ? groups : undefined, isLoading: false, isError: false }
  },
}))
vi.mock('@/hooks/useLiveEvents', () => ({ useLiveEvents: () => ({ connectionState: 'open' }) }))
vi.mock('@/components/common/BranchSelector', () => ({ BranchSelector: () => null }))
vi.mock('@/components/common/RangeSelector', () => ({ RangeSelector: () => null }))
vi.mock('@/components/common/SavedFiltersMenu', () => ({ SavedFiltersMenu: () => null }))
vi.mock('@/components/blocked/EventDetailSheet', () => ({ EventDetailSheet: () => null }))
vi.mock('@/components/analytics/StackedAreaOverTime', () => ({ StackedAreaOverTime: () => null }))
vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  downloadBlockedGroups: (...args: unknown[]) => downloadBlockedGroups(...args),
}))
vi.mock('@/lib/auth-store', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/lib/auth-store')>()
  return {
    ...actual,
    useAuthStore: (selector: (s: { role: string }) => unknown) => selector({ role }),
  }
})

const { default: BlockedPage } = await import('@/pages/BlockedPage')

const renderPage = (path = '/blocked') =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <BlockedPage />
    </MemoryRouter>,
  )

describe('BlockedPage', () => {
  beforeEach(() => {
    eventsCalls.length = 0
    groupCalls.length = 0
    summaryCalls.length = 0
    downloadBlockedGroups.mockClear()
    role = 'admin'
  })

  it('lists real blocks by default and applies the shared filters to the requests', async () => {
    const user = userEvent.setup()
    renderPage()
    expect(eventsCalls.at(-1)).toMatchObject({ blockedOnly: true, blockKind: 'denied', enabled: true })
    expect(groupCalls.at(-1)).toMatchObject({ enabled: false })

    await user.type(screen.getByRole('textbox', { name: 'Domain' }), 'crl.{Enter}')
    expect(eventsCalls.at(-1)?.filters).toMatchObject({ domains: 'crl.' })
    // the applied term shows as a removable chip
    await user.click(screen.getByRole('button', { name: 'Remove the "crl." filter' }))
    expect(eventsCalls.at(-1)?.filters).toMatchObject({ domains: '' })
  })

  it('summarises and groups the filtered blocks, and drills down on a row click', async () => {
    const user = userEvent.setup()
    renderPage('/blocked?view=analysis&d=crl.')
    expect(summaryCalls.at(-1)).toMatchObject({ kind: 'denied', filters: { domains: 'crl.' } })
    expect(groupCalls.at(-1)).toMatchObject({ enabled: true, group: 'domain', sort: 'requests', offset: 0 })
    expect(screen.getByText('1,309')).toBeInTheDocument() // client IPs card
    expect(screen.getByText('214')).toBeInTheDocument() // users card

    await user.click(screen.getByText('crl.usertrust.com'))
    expect(groupCalls.at(-1)).toMatchObject({ group: 'client', filters: { domains: '=crl.usertrust.com' } })

    await user.click(screen.getByRole('tab', { name: 'Subnet (/24)' }))
    expect(groupCalls.at(-1)).toMatchObject({ group: 'subnet' })
  })

  it('exports just the listed values, for admins and auditors only', async () => {
    const user = userEvent.setup()
    const { unmount } = renderPage('/blocked?view=analysis&d=crl.')
    await user.click(screen.getByRole('button', { name: /List only \(Domain\)/ }))
    expect(downloadBlockedGroups).toHaveBeenCalledWith(
      'csv',
      expect.objectContaining({ columns: 'key', group: 'domain', kind: 'denied', domains: 'crl.' }),
    )
    unmount()

    role = 'viewer'
    renderPage('/blocked?view=analysis')
    expect(screen.queryByRole('button', { name: /Excel/ })).not.toBeInTheDocument()
  })
})
