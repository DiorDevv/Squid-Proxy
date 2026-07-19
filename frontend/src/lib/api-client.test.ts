import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiFetch } from '@/lib/api-client'
import { useAuthStore } from '@/lib/auth-store'

function makeJwt(payload: object): string {
  const base64Url = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${base64Url({ alg: 'HS256', typ: 'JWT' })}.${base64Url(payload)}.signature`
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  })
}

describe('apiFetch silent refresh (post-reload session survival)', () => {
  beforeEach(() => {
    useAuthStore.setState({ accessToken: null, role: null, email: null, status: 'checking' })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  // Regression test for the bug fixed in api-client.ts/auth-store.ts:
  // doRefresh() used to require `role && email` already in the store before
  // accepting a fresh access token from /api/auth/refresh. After a hard
  // page reload, `email` is null (see useAuth.bootstrap) until the user
  // logs in again explicitly -- so a 401 hit after reload would silently
  // discard a *successful* server-side refresh and force a logout. This
  // test proves a 401 followed by a successful refresh (with email still
  // null) now transparently retries and succeeds.
  it('recovers from a 401 via silent refresh even when email is null', async () => {
    useAuthStore.setState({
      accessToken: 'expiring-token',
      role: 'viewer',
      email: null,
      status: 'authenticated',
    })

    const newAccessToken = makeJwt({ sub: 'user-1', role: 'viewer' })
    const fetchMock = vi
      .fn()
      // 1) Original request fails with an expired token.
      .mockResolvedValueOnce(jsonResponse({ detail: 'Token expired' }, 401))
      // 2) Refresh call succeeds and returns a fresh access token.
      .mockResolvedValueOnce(
        jsonResponse({ access_token: newAccessToken, token_type: 'bearer', expires_in_seconds: 1200 }),
      )
      // 3) Retried original request succeeds with the new token.
      .mockResolvedValueOnce(jsonResponse({ ok: true }))

    vi.stubGlobal('fetch', fetchMock)

    const result = await apiFetch<{ ok: boolean }>('/api/summary')

    expect(result).toEqual({ ok: true })
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(String(fetchMock.mock.calls[1]![0])).toContain('/api/auth/refresh')

    const state = useAuthStore.getState()
    expect(state.accessToken).toBe(newAccessToken)
    expect(state.status).toBe('authenticated')
    // The critical assertion: session survives, user is NOT logged out.
    expect(state.email).toBeNull()
  })

  it('logs the user out if the refresh call itself fails', async () => {
    useAuthStore.setState({
      accessToken: 'expiring-token',
      role: 'viewer',
      email: null,
      status: 'authenticated',
    })

    const fetchMock = vi
      .fn()
      .mockResolvedValueOnce(jsonResponse({ detail: 'Token expired' }, 401))
      .mockResolvedValueOnce(jsonResponse({ detail: 'Invalid or expired session.' }, 401))

    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetch('/api/summary')).rejects.toThrow('Session expired')

    expect(useAuthStore.getState().status).toBe('unauthenticated')
    expect(useAuthStore.getState().accessToken).toBeNull()
  })

  it('does not attempt a refresh when there is no access token at all', async () => {
    const fetchMock = vi.fn().mockResolvedValueOnce(jsonResponse({ detail: 'Unauthorized' }, 401))
    vi.stubGlobal('fetch', fetchMock)

    await expect(apiFetch('/api/summary')).rejects.toThrow()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
