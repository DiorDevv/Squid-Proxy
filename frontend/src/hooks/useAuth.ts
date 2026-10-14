import { useCallback } from 'react'
import { api } from '@/lib/api-client'
import { decodeAccessTokenBranch, decodeAccessTokenRole, useAuthStore } from '@/lib/auth-store'
import { queryClient } from '@/lib/queryClient'
import type { LoginResponse, Role } from '@/types/auth'

export function useAuth() {
  const {
    accessToken,
    role,
    username,
    fullName,
    branch,
    branches,
    permissions,
    mustChangePassword,
    status,
    setAuth,
    clearAuth,
    setChecking,
  } = useAuthStore()

  const adopt = useCallback(
    (response: LoginResponse) => {
      // Discard any cached data fetched under a previous identity (e.g. a
      // stale branch list from an earlier admin session) before adopting
      // the new one.
      queryClient.clear()
      setAuth({
        accessToken: response.access_token as string,
        role: response.role as Role,
        username: response.username,
        fullName: response.full_name,
        branch: response.branch,
        branches: response.branches ?? [],
        permissions: response.permissions ?? [],
        mustChangePassword: response.must_change_password,
      })
    },
    [setAuth],
  )

  // Returns the challenge_token when the account has TOTP enabled (password
  // was right, but a code is still needed -- see completeMfaLogin) instead
  // of completing auth itself; returns null when login finished normally.
  const login = useCallback(
    async (loginName: string, password: string): Promise<string | null> => {
      const response = await api.login(loginName, password)
      if (response.mfa_required) {
        return response.challenge_token
      }
      adopt(response)
      return null
    },
    [adopt],
  )

  const completeMfaLogin = useCallback(
    async (challengeToken: string, code: string) => {
      adopt(await api.verifyMfa(challengeToken, code))
    },
    [adopt],
  )

  const logout = useCallback(async () => {
    try {
      await api.logout()
    } catch {
      // best-effort; clear local state regardless
    }
    clearAuth()
    queryClient.clear()
  }, [clearAuth])

  /** Called once on app mount: the refresh token is an httpOnly cookie, so a
   * hard page reload can silently re-establish a session without a login
   * form. /api/auth/refresh returns only a new access token, so role/branch
   * come from decoding it and the profile (username, name, whether the
   * password must still be changed) from /api/auth/me. */
  const bootstrap = useCallback(async () => {
    setChecking()
    try {
      const response = await api.refresh()
      const decodedRole = decodeAccessTokenRole(response.access_token)
      if (!decodedRole) throw new Error('Could not determine role from token')
      useAuthStore.setState({ accessToken: response.access_token })
      const me = await api.me()
      useAuthStore.setState({
        role: decodedRole,
        branch: decodeAccessTokenBranch(response.access_token),
        branches: me.branches ?? [],
        permissions: me.permissions ?? [],
        username: me.username,
        fullName: me.full_name,
        mustChangePassword: me.must_change_password,
        status: 'authenticated',
      })
    } catch {
      clearAuth()
    }
  }, [clearAuth, setChecking])

  return {
    accessToken,
    role,
    username,
    fullName,
    branch,
    branches,
    permissions,
    mustChangePassword,
    status,
    login,
    completeMfaLogin,
    logout,
    bootstrap,
  }
}
