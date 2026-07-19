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
  status: 'checking' | 'authenticated' | 'unauthenticated'
  setAuth: (data: { accessToken: string; role: Role; email: string }) => void
  /** Updates the access token (and its role claim) only, leaving `email`
   * untouched -- used by silent token refresh, which never learns the
   * user's email (see doRefresh in api-client.ts). Deliberately distinct
   * from `setAuth`, which represents a fresh login and always knows email. */
  setAccessToken: (accessToken: string, role: Role) => void
  clearAuth: () => void
  setChecking: () => void
}

export const useAuthStore = create<AuthState>((set) => ({
  accessToken: null,
  role: null,
  email: null,
  status: 'checking',
  setAuth: ({ accessToken, role, email }) =>
    set({ accessToken, role, email, status: 'authenticated' }),
  setAccessToken: (accessToken, role) => set({ accessToken, role, status: 'authenticated' }),
  clearAuth: () => set({ accessToken: null, role: null, email: null, status: 'unauthenticated' }),
  setChecking: () => set({ status: 'checking' }),
}))

export function getAccessToken(): string | null {
  return useAuthStore.getState().accessToken
}

/**
 * Decodes the JWT payload without verifying its signature -- fine for
 * populating UI state (e.g. showing/hiding the admin-only nav item), since
 * the backend independently re-validates and enforces the role on every
 * request. Never treat this as an authorization decision by itself.
 */
export function decodeAccessTokenRole(token: string): Role | null {
  try {
    const payloadSegment = token.split('.')[1]
    if (!payloadSegment) return null
    const json = atob(payloadSegment.replace(/-/g, '+').replace(/_/g, '/'))
    const payload = JSON.parse(json) as { role?: string }
    return payload.role === 'admin' || payload.role === 'viewer' ? payload.role : null
  } catch {
    return null
  }
}
