import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { BlockedDomainsResponse } from '@/types/api'

const eventsCalls: Record<string, unknown>[] = []
const domainCalls: Record<string, unknown>[] = []
const downloadBlockedDomains = vi.fn().mockResolvedValue(undefined)
let role = 'admin'

const domainsData: BlockedDomainsResponse = {
  items: [
    {
      domain: 'crl.usertrust.com',
      denied_count: 25616,
      auth_count: 331,
      client_count: 806,
      branches: ['filial', 'main'],
      proxies: ['172.25.42.77'],
      first_seen: '2026-10-06T11:00:00Z',
      last_seen: '2026-10-13T11:00:00Z',
    },
  ],
  total: 1,
  limit: 50,
  offset: 0,
  denied_total: 25616,
  auth_total: 331,
  available_proxies: ['172.25.42.24', '172.25.42.77'],
}

vi.mock('@/hooks/useEvents', () => ({
  useEvents: (params: Record<string, unknown>) => {
    eventsCalls.push(params)
    return { data: { items: [], total: 0, limit: 50, offset: 0 }, isLoading: false, isError: false }
  },
}))
vi.mock('@/hooks/useBlockedDomains', () => ({
  useBlockedDomains: (params: Record<string, unknown>) => {
    domainCalls.push(params)
    return { data: params.enabled ? domainsData : undefined, isLoading: false, isError: false }
  },
}))
vi.mock('@/hooks/useLiveEvents', () => ({ useLiveEvents: () => ({ connectionState: 'open' }) }))
vi.mock('@/components/common/BranchSelector', () => ({ BranchSelector: () => null }))
vi.mock('@/components/common/RangeSelector', () => ({ RangeSelector: () => null }))
vi.mock('@/components/common/SavedFiltersMenu', () => ({ SavedFiltersMenu: () => null }))
vi.mock('@/components/blocked/EventDetailSheet', () => ({ EventDetailSheet: () => null }))
vi.mock('@/lib/api-client', async (importOriginal) => ({
  ...(await importOriginal<object>()),
  downloadBlockedDomains: (...args: unknown[]) => downloadBlockedDomains(...args),
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
    domainCalls.length = 0
    downloadBlockedDomains.mockClear()
    role = 'admin'
  })

  it('lists real blocks by default, without 407 login challenges', () => {
    renderPage()
    expect(eventsCalls.at(-1)).toMatchObject({ blockedOnly: true, blockKind: 'denied', enabled: true })
    expect(domainCalls.at(-1)).toMatchObject({ enabled: false })
  })

  it('groups by domain on the Domains tab and exports just the names', async () => {
    const user = userEvent.setup()
    renderPage()
    await user.click(screen.getByRole('tab', { name: 'Domains' }))

    expect(domainCalls.at(-1)).toMatchObject({ enabled: true, kind: 'denied', sort: 'requests', offset: 0 })
    expect(eventsCalls.at(-1)).toMatchObject({ enabled: false })
    expect(screen.getByText('crl.usertrust.com')).toBeInTheDocument()
    expect(screen.getByText('1 domains · 403: 25,616 · 407: 331')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Domains only/ }))
    expect(downloadBlockedDomains).toHaveBeenCalledWith(
      'csv',
      expect.objectContaining({ columns: 'domain', kind: 'denied' }),
    )
  })

  it('opens straight on the Domains tab from the URL, export for admins only', () => {
    role = 'viewer'
    renderPage('/blocked?view=domains')
    expect(screen.getByText('crl.usertrust.com')).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Excel/ })).not.toBeInTheDocument()
  })
})
