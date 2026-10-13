import { create } from 'zustand'
import type { Role } from '@/types/auth'

/**
 * Access token lives in memory only (never localStorage) to limit XSS
 * exfiltration surface. It's lost on a hard page refresh; App.tsx calls
 * /api/auth/refresh on bootstrap (the refresh token is an httpOnly cookie)
 * to silently reissue it, then /api/auth/me for the profile fields the
 * token doesn't carry. See ARCHITECTURE.md.
 */
interface AuthState {
  accessToken: string | null
  role: Role | null
  username: string | null
  fullName: string | null
  // null = unrestricted (every user before branch-scoping existed); a
  // non-null value means this account can only ever see that one branch's
  // data (enforced server-side, see api/deps.py's resolve_branch -- this is
  // just for UI state, e.g. deciding whether to show a branch picker).
  branch: string | null
  // Signed in with an admin-issued temporary password: the app shows only
  // the change-password screen until it's changed (the API refuses
  // everything else anyway, see api-client's password_change_required).
  mustChangePassword: boolean
  status: 'checking' | 'authenticated' | 'unauthenticated'
  setAuth: (data: {
    accessToken: string
    role: Role
    username: string | null
    fullName: string | null
    branch: string | null
    mustChangePassword: boolean
  }) => void
  /** Updates the access token (and its role/branch claims) only, leaving
   * the profile fields untouched -- used by silent token refresh, whose
   * response carries nothing but the token (see doRefresh in
   * api-client.ts). Deliberately distinct from `setAuth`, which represents
   * a fresh login. */
  setAccessToken: (accessToken: string, role: Role, branch: string | null) => void
  setProfile: (data: { username: string; fullName: string; mustChangePassword: boolean }) => void
  setMustChangePassword: (value: boolean) => void
  clearAuth: () => void
  setChecking: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  role: null,
  username: null,
  fullName: null,
  branch: null,
  mustChangePassword: false,
  status: 'checking',
  setAuth: ({ accessToken, role, username, fullName, branch, mustChangePassword }) =>
    set({
      accessToken,
      role,
      username,
      fullName,
      branch,
      mustChangePassword,
      status: 'authenticated',
    }),
  setAccessToken: (accessToken, role, branch) =>
    set({ accessToken, role, branch, status: 'authenticated' }),
  setProfile: ({ username, fullName, mustChangePassword }) =>
    set({ username, fullName, mustChangePassword }),
  setMustChangePassword: (mustChangePassword) => set({ mustChangePassword }),
  clearAuth: () =>
    set({
      accessToken: null,
      role: null,
      username: null,
      fullName: null,
      branch: null,
      mustChangePassword: false,
      status: 'unauthenticated',
    }),
  setChecking: () => set({ status: 'checking' }),
}))

export function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken
}

/** superadmin satisfies every admin check (see backend api/deps.require_admin). */
export function isAdminRole(role: Role | null | undefined): boolean {
  return role === 'superadmin' || role === 'admin'
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

const ROLES: readonly Role[] = ['superadmin', 'admin', 'viewer', 'auditor']

/**
 * Decodes the JWT payload without verifying its signature -- fine for
 * populating UI state (e.g. showing/hiding the admin-only nav item), since
 * the backend independently re-validates and enforces the role on every
 * request. Never treat this as an authorization decision by itself.
 */
export function decodeAccessTokenRole(token: string): Role | null {
  const payload = decodeTokenPayload(token)
  const role = payload?.role
  return ROLES.includes(role as Role) ? (role as Role) : null
}

/** Same non-verifying decode as decodeAccessTokenRole, for the branch
 * claim -- UI-only (e.g. hiding the branch picker for a scoped user), the
 * backend is the actual enforcement point. */
export function decodeAccessTokenBranch(token: string): string | null {
  const payload = decodeTokenPayload(token)
  const branch = payload?.branch
  return typeof branch === 'string' ? branch : null
}
