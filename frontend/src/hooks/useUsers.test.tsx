import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCreateUser, useUsers } from '@/hooks/useUsers'
import { api } from '@/lib/api-client'
import type { UserSummary } from '@/types/api'

function makeUser(overrides: Partial<UserSummary>): UserSummary {
  return {
    id: '1',
    username: 'admin',
    full_name: '',
    email: null,
    note: null,
    role: 'superadmin',
    branch: null,
    branches: null,
    permissions: null,
    effective_permissions: [],
    expires_at: null,
    is_active: true,
    must_change_password: false,
    totp_enabled: false,
    last_login_at: null,
    last_login_ip: null,
    password_changed_at: null,
    created_by: null,
    created_at: '2026-01-01T00:00:00Z',
    active_sessions: 0,
    throttled: false,
    ...overrides,
  }
}

vi.mock('@/lib/api-client', async () => {
  const actual = await vi.importActual<typeof import('@/lib/api-client')>('@/lib/api-client')
  return {
    ...actual,
    api: {
      ...actual.api,
      listUsers: vi.fn(),
      createUser: vi.fn(),
    },
  }
})

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

const SAMPLE_USERS: UserSummary[] = [makeUser({})]

describe('useUsers', () => {
  beforeEach(() => {
    vi.mocked(api.listUsers).mockReset()
    vi.mocked(api.createUser).mockReset()
  })

  it('fetches and returns the user list', async () => {
    vi.mocked(api.listUsers).mockResolvedValueOnce(SAMPLE_USERS)

    const { result } = renderHook(() => useUsers(), { wrapper })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(result.current.data).toEqual(SAMPLE_USERS)
  })

  it('surfaces a fetch error', async () => {
    vi.mocked(api.listUsers).mockRejectedValueOnce(new Error('network down'))

    const { result } = renderHook(() => useUsers(), { wrapper })

    await waitFor(() => expect(result.current.isError).toBe(true))
  })
})

describe('useCreateUser', () => {
  beforeEach(() => {
    vi.mocked(api.createUser).mockReset()
  })

  it('calls api.createUser with the given payload and returns the temporary password', async () => {
    const created = {
      user: makeUser({ id: '2', username: 'new.viewer', role: 'viewer' }),
      temporary_password: 'Tmp-Pass-1234!',
    }
    vi.mocked(api.createUser).mockResolvedValueOnce(created)
    const payload = {
      username: 'new.viewer',
      full_name: 'New Viewer',
      note: null,
      email: null,
      role: 'viewer' as const,
      branches: ['main', 'filial'],
      permissions: ['export' as const],
      expires_at: null,
    }

    const { result } = renderHook(() => useCreateUser(), { wrapper })
    result.current.mutate(payload)

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.createUser).toHaveBeenCalledWith(payload)
    expect(result.current.data?.temporary_password).toBe('Tmp-Pass-1234!')
  })
})
