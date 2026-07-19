import { beforeEach, describe, expect, it } from 'vitest'
import { decodeAccessTokenRole, getAccessToken, useAuthStore } from '@/lib/auth-store'

function makeJwt(payload: object): string {
  const base64Url = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${base64Url({ alg: 'HS256', typ: 'JWT' })}.${base64Url(payload)}.signature`
}

beforeEach(() => {
  useAuthStore.setState({ accessToken: null, role: null, email: null, status: 'checking' })
})

describe('useAuthStore', () => {
  it('setAuth stores token, role, and email and marks authenticated', () => {
    useAuthStore.getState().setAuth({ accessToken: 'tok', role: 'admin', email: 'a@example.com' })

    const state = useAuthStore.getState()
    expect(state.accessToken).toBe('tok')
    expect(state.role).toBe('admin')
    expect(state.email).toBe('a@example.com')
    expect(state.status).toBe('authenticated')
  })

  // Regression test for the silent-session-death bug: a session restored
  // via a hard reload (bootstrap) has email=null since /api/auth/refresh
  // never returns it. A later silent token refresh (setAccessToken) must
  // update the token without requiring or clobbering email.
  it('setAccessToken updates the token without requiring or touching email', () => {
    useAuthStore.setState({ accessToken: 'old-tok', role: 'viewer', email: null, status: 'authenticated' })

    useAuthStore.getState().setAccessToken('new-tok', 'viewer')

    const state = useAuthStore.getState()
    expect(state.accessToken).toBe('new-tok')
    expect(state.role).toBe('viewer')
    expect(state.email).toBeNull()
    expect(state.status).toBe('authenticated')
  })

  it('setAccessToken preserves an existing email if one is set', () => {
    useAuthStore.setState({
      accessToken: 'old-tok',
      role: 'admin',
      email: 'known@example.com',
      status: 'authenticated',
    })

    useAuthStore.getState().setAccessToken('new-tok', 'admin')

    expect(useAuthStore.getState().email).toBe('known@example.com')
  })

  it('clearAuth resets everything to unauthenticated', () => {
    useAuthStore.getState().setAuth({ accessToken: 'tok', role: 'admin', email: 'a@example.com' })

    useAuthStore.getState().clearAuth()

    const state = useAuthStore.getState()
    expect(state.accessToken).toBeNull()
    expect(state.role).toBeNull()
    expect(state.email).toBeNull()
    expect(state.status).toBe('unauthenticated')
  })

  it('setChecking sets status without touching other fields', () => {
    useAuthStore.getState().setAuth({ accessToken: 'tok', role: 'admin', email: 'a@example.com' })

    useAuthStore.getState().setChecking()

    const state = useAuthStore.getState()
    expect(state.status).toBe('checking')
    expect(state.accessToken).toBe('tok')
  })

  it('getAccessToken reads the current token from the store', () => {
    useAuthStore.getState().setAuth({ accessToken: 'read-me', role: 'viewer', email: 'x@example.com' })
    expect(getAccessToken()).toBe('read-me')
  })
})

describe('decodeAccessTokenRole', () => {
  it('decodes a valid admin role from the payload', () => {
    const token = makeJwt({ sub: 'user-1', role: 'admin' })
    expect(decodeAccessTokenRole(token)).toBe('admin')
  })

  it('decodes a valid viewer role from the payload', () => {
    const token = makeJwt({ sub: 'user-1', role: 'viewer' })
    expect(decodeAccessTokenRole(token)).toBe('viewer')
  })

  it('returns null for an unrecognized role value', () => {
    const token = makeJwt({ sub: 'user-1', role: 'superuser' })
    expect(decodeAccessTokenRole(token)).toBeNull()
  })

  it('returns null for a malformed token', () => {
    expect(decodeAccessTokenRole('not-a-jwt')).toBeNull()
  })

  it('returns null for an empty string', () => {
    expect(decodeAccessTokenRole('')).toBeNull()
  })
})
