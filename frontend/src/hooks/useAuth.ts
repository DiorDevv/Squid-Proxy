import { useCallback } from 'react'
import { api } from '@/lib/api-client'
import { decodeAccessTokenRole, useAuthStore } from '@/lib/auth-store'

export function useAuth() {
  const { accessToken, role, email, status, setAuth, clearAuth, setChecking } = useAuthStore()

  const login = useCallback(
    async (loginEmail: string, password: string) => {
      const response = await api.login(loginEmail, password)
      setAuth({ accessToken: response.access_token, role: response.role, email: response.email })
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
        email: null,
        status: 'authenticated',
      })
    } catch {
      clearAuth()
    }
  }, [clearAuth, setChecking])

  return { accessToken, role, email, status, login, logout, bootstrap }
}
