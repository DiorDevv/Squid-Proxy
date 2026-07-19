import type { ReactNode } from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { renderHook, waitFor } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { useCreateUser, useUsers } from '@/hooks/useUsers'
import { api } from '@/lib/api-client'
import type { UserSummary } from '@/types/api'

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

const SAMPLE_USERS: UserSummary[] = [
  { id: '1', email: 'admin@example.com', role: 'admin', created_at: '2026-01-01T00:00:00Z' },
]

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

  it('calls api.createUser with the given payload', async () => {
    const created: UserSummary = {
      id: '2',
      email: 'new@example.com',
      role: 'viewer',
      created_at: '2026-01-02T00:00:00Z',
    }
    vi.mocked(api.createUser).mockResolvedValueOnce(created)

    const { result } = renderHook(() => useCreateUser(), { wrapper })
    result.current.mutate({ email: 'new@example.com', password: 'password123', role: 'viewer' })

    await waitFor(() => expect(result.current.isSuccess).toBe(true))
    expect(api.createUser).toHaveBeenCalledWith({
      email: 'new@example.com',
      password: 'password123',
      role: 'viewer',
    })
  })
})
