import { beforeEach, describe, expect, it } from 'vitest'
import { decodeAccessTokenBranch, decodeAccessTokenRole, getAccessToken, useAuthStore } from '@/lib/auth-store'

function makeJwt(payload: object): string {
  const base64Url = (obj: object) =>
    btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
  return `${base64Url({ alg: 'HS256', typ: 'JWT' })}.${base64Url(payload)}.signature`
}

beforeEach(() => {
  useAuthStore.setState({
    accessToken: null,
    role: null,
    username: null,
    fullName: null,
    branch: null,
    mustChangePassword: false,
    status: 'checking',
  })
})

describe('useAuthStore', () => {
  it('setAuth stores token, role, username, and branch and marks authenticated', () => {
    useAuthStore.getState().setAuth({ accessToken: 'tok', role: 'admin', username: 'a', fullName: null, mustChangePassword: false, branch: null })

    const state = useAuthStore.getState()
    expect(state.accessToken).toBe('tok')
    expect(state.role).toBe('admin')
    expect(state.username).toBe('a')
    expect(state.branch).toBeNull()
    expect(state.status).toBe('authenticated')
  })

  it('setAuth stores a non-null branch for a scoped user', () => {
    useAuthStore
      .getState()
      .setAuth({ accessToken: 'tok', role: 'viewer', username: 'a', fullName: null, mustChangePassword: false, branch: 'filiallar' })

    expect(useAuthStore.getState().branch).toBe('filiallar')
  })

  // Regression test for the silent-session-death bug: a silent token
  // refresh (setAccessToken) must update the token without requiring or
  // clobbering profile fields, which /api/auth/refresh never returns.
  it('setAccessToken updates the token without requiring or touching username', () => {
    useAuthStore.setState({
      accessToken: 'old-tok',
      role: 'viewer',
      username: null,
      branch: null,
      status: 'authenticated',
    })

    useAuthStore.getState().setAccessToken('new-tok', 'viewer', null)

    const state = useAuthStore.getState()
    expect(state.accessToken).toBe('new-tok')
    expect(state.role).toBe('viewer')
    expect(state.username).toBeNull()
    expect(state.status).toBe('authenticated')
  })

  it('setAccessToken preserves an existing username if one is set', () => {
    useAuthStore.setState({
      accessToken: 'old-tok',
      role: 'admin',
      username: 'known',
      branch: null,
      status: 'authenticated',
    })

    useAuthStore.getState().setAccessToken('new-tok', 'admin', null)

    expect(useAuthStore.getState().username).toBe('known')
  })

  it('clearAuth resets everything to unauthenticated', () => {
    useAuthStore
      .getState()
      .setAuth({ accessToken: 'tok', role: 'admin', username: 'a', fullName: null, mustChangePassword: false, branch: 'hq' })

    useAuthStore.getState().clearAuth()

    const state = useAuthStore.getState()
    expect(state.accessToken).toBeNull()
    expect(state.role).toBeNull()
    expect(state.username).toBeNull()
    expect(state.mustChangePassword).toBe(false)
    expect(state.branch).toBeNull()
    expect(state.status).toBe('unauthenticated')
  })

  it('setChecking sets status without touching other fields', () => {
    useAuthStore
      .getState()
      .setAuth({ accessToken: 'tok', role: 'admin', username: 'a', fullName: null, mustChangePassword: false, branch: null })

    useAuthStore.getState().setChecking()

    const state = useAuthStore.getState()
    expect(state.status).toBe('checking')
    expect(state.accessToken).toBe('tok')
  })

  it('getAccessToken reads the current token from the store', () => {
    useAuthStore
      .getState()
      .setAuth({ accessToken: 'read-me', role: 'viewer', username: 'x', fullName: null, mustChangePassword: false, branch: null })
    expect(getAccessToken()).toBe('read-me')
  })
})

describe('decodeAccessTokenRole', () => {
  it('decodes a valid admin role from the payload', () => {
    const token = makeJwt({ sub: 'user-1', role: 'admin' })
    expect(decodeAccessTokenRole(token)).toBe('admin')
  })

  it('decodes the superadmin role from the payload', () => {
    const token = makeJwt({ sub: 'user-1', role: 'superadmin' })
    expect(decodeAccessTokenRole(token)).toBe('superadmin')
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

describe('decodeAccessTokenBranch', () => {
  it('decodes a branch string from the payload', () => {
    const token = makeJwt({ sub: 'user-1', role: 'viewer', branch: 'filiallar' })
    expect(decodeAccessTokenBranch(token)).toBe('filiallar')
  })

  it('returns null when the payload has no branch claim (unrestricted, or a pre-existing token)', () => {
    const token = makeJwt({ sub: 'user-1', role: 'admin' })
    expect(decodeAccessTokenBranch(token)).toBeNull()
  })

  it('returns null when the branch claim is explicitly null', () => {
    const token = makeJwt({ sub: 'user-1', role: 'admin', branch: null })
    expect(decodeAccessTokenBranch(token)).toBeNull()
  })

  it('returns null for a malformed token', () => {
    expect(decodeAccessTokenBranch('not-a-jwt')).toBeNull()
  })
})
