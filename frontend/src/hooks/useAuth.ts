import { useCallback } from 'react'
import { api } from '@/lib/api-client'
import { decodeAccessTokenBranch, decodeAccessTokenRole, useAuthStore } from '@/lib/auth-store'
import { queryClient } from '@/lib/queryClient'
import type { Role } from '@/types/auth'

export function useAuth() {
  const { accessToken, role, email, branch, status, setAuth, clearAuth, setChecking } = useAuthStore()

  // Returns the challenge_token when the account has TOTP enabled (password
  // was right, but a code is still needed -- see completeMfaLogin) instead
  // of completing auth itself; returns null when login finished normally
  // (no 2FA on this account), matching every caller's pre-2FA behavior.
  const login = useCallback(async (loginEmail: string, password: string): Promise<string | null> => {
    const response = await api.login(loginEmail, password)
    if (response.mfa_required) {
      return response.challenge_token
    }
    // Discard any cached data fetched under a previous identity (e.g. a stale
    // branch list from an earlier admin session) before adopting the new one.
    queryClient.clear()
    setAuth({
      accessToken: response.access_token as string,
      role: response.role as Role,
      email: response.email as string,
      branch: response.branch,
    })
    return null
  }, [setAuth])

  const completeMfaLogin = useCallback(
    async (challengeToken: string, code: string) => {
      const response = await api.verifyMfa(challengeToken, code)
      queryClient.clear()
      setAuth({
        accessToken: response.access_token as string,
        role: response.role as Role,
        email: response.email as string,
        branch: response.branch,
      })
    },
    [setAuth],
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
   * form. /api/auth/refresh only returns a new access token (no email), so
   * role is recovered by decoding the token and email is left blank until
   * the user's next explicit login. */
  const bootstrap = useCallback(async () => {
    setChecking()
    try {
      const response = await api.refresh()
      const decodedRole = decodeAccessTokenRole(response.access_token)
      if (!decodedRole) throw new Error('Could not determine role from token')
      useAuthStore.setState({
        accessToken: response.access_token,
        role: decodedRole,
        branch: decodeAccessTokenBranch(response.access_token),
        email: null,
        status: 'authenticated',
      })
    } catch {
      clearAuth()
    }
  }, [clearAuth, setChecking])

  return { accessToken, role, email, branch, status, login, completeMfaLogin, logout, bootstrap }
}
