import { create } from 'zustand'
import type { Role } from '@/types/auth'

/**
 * Access token lives in memory only (never localStorage) to limit XSS
 * exfiltration surface. It's lost on a hard page refresh; App.tsx calls
 * /api/auth/refresh on bootstrap (the refresh token is an httpOnly cookie)
 * to silently reissue it. See ARCHITECTURE.md.
 */
interface AuthState {
  accessToken: string | null
  role: Role | null
  email: string | null
  // null = unrestricted (every user before branch-scoping existed); a
  // non-null value means this account can only ever see that one branch's
  // data (enforced server-side, see api/deps.py's resolve_branch -- this is
  // just for UI state, e.g. deciding whether to show a branch picker).
  branch: string | null
  status: 'checking' | 'authenticated' | 'unauthenticated'
  setAuth: (data: { accessToken: string; role: Role; email: string; branch: string | null }) => void
  /** Updates the access token (and its role/branch claims) only, leaving
   * `email` untouched -- used by silent token refresh, which never learns
   * the user's email (see doRefresh in api-client.ts). Deliberately
   * distinct from `setAuth`, which represents a fresh login and always
   * knows email. */
  setAccessToken: (accessToken: string, role: Role, branch: string | null) => void
  clearAuth: () => void
  setChecking: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  role: null,
  email: null,
  branch: null,
  status: 'checking',
  setAuth: ({ accessToken, role, email, branch }) =>
    set({ accessToken, role, email, branch, status: 'authenticated' }),
  setAccessToken: (accessToken, role, branch) =>
    set({ accessToken, role, branch, status: 'authenticated' }),
  clearAuth: () =>
    set({ accessToken: null, role: null, email: null, branch: null, status: 'unauthenticated' }),
  setChecking: () => set({ status: 'checking' }),
}))

export function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken
}

function decodeTokenPayload(token: string): Record<string, unknown> | null {
  try {
    const payloadSegment = token.split('.')[1]
    if (!payloadSegment) return null
    const json = atob(payloadSegment.replace(/-/g, '+').replace(/_/g, '/'))
    return JSON.parse(json) as Record<string, unknown>
  } catch {
    return null
  }
}

/**
 * Decodes the JWT payload without verifying its signature -- fine for
 * populating UI state (e.g. showing/hiding the admin-only nav item), since
 * the backend independently re-validates and enforces the role on every
 * request. Never treat this as an authorization decision by itself.
 */
export function decodeAccessTokenRole(token: string): Role | null {
  const payload = decodeTokenPayload(token)
  const role = payload?.role
  return role === 'admin' || role === 'viewer' ? role : null
}

/** Same non-verifying decode as decodeAccessTokenRole, for the branch
 * claim -- UI-only (e.g. hiding the branch picker for a scoped user), the
 * backend is the actual enforcement point. */
export function decodeAccessTokenBranch(token: string): string | null {
  const payload = decodeTokenPayload(token)
  const branch = payload?.branch
  return typeof branch === 'string' ? branch : null
}
