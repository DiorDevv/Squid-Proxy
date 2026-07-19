import { API_BASE_URL } from '@/lib/constants'
import { decodeAccessTokenRole, getAccessToken, useAuthStore } from '@/lib/auth-store'
import { translate, useLocaleStore } from '@/i18n'
import type { LoginResponse, RefreshResponse, Role, WsTicketResponse } from '@/types/auth'
import type { UserSummary } from '@/types/api'

export class ApiError extends Error {
  status: number
  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

let refreshInFlight: Promise<boolean> | null = null

function buildUrl(path: string, searchParams?: RequestOptions['searchParams']): string {
  // API_BASE_URL may be relative (e.g. "" in the Docker image, where nginx
  // proxies /api and /ws on the same origin the SPA is served from) or
  // absolute (e.g. "http://localhost:8000" in local dev).
  const url = new URL(`${API_BASE_URL}${path}`, window.location.origin)
  if (searchParams) {
    for (const [key, value] of Object.entries(searchParams)) {
      if (value !== undefined) url.searchParams.set(key, String(value))
    }
  }
  return url.toString()
}

async function doRefresh(): Promise<boolean> {
  try {
    const response = await fetch(buildUrl('/api/auth/refresh'), {
      method: 'POST',
      credentials: 'include',
    })
    if (!response.ok) return false
    const body = (await response.json()) as RefreshResponse
    // The refresh response never includes email (the refresh cookie doesn't
    // carry it), so role is recovered from the token itself rather than
    // requiring an email already in the store -- a session restored via a
    // hard reload (where email is null, see useAuth.bootstrap) must still be
    // able to silently refresh past its first access-token expiry.
    const role = decodeAccessTokenRole(body.access_token)
    if (!role) return false
    useAuthStore.getState().setAccessToken(body.access_token, role)
    return true
  } catch {
    return false
  }
}

async function refreshOnce(): Promise<boolean> {
  if (!refreshInFlight) {
    refreshInFlight = doRefresh().finally(() => {
      refreshInFlight = null
    })
  }
  return refreshInFlight
}

interface RequestOptions {
  method?: string
  body?: unknown
  searchParams?: Record<string, string | number | boolean | undefined>
  skipAuthRetry?: boolean
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, searchParams, skipAuthRetry } = options
  const token = getAccessToken()

  const response = await fetch(buildUrl(path, searchParams), {
    method,
    credentials: 'include',
    headers: {
      ...(body ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  })

  if (response.status === 401 && !skipAuthRetry && token) {
    const refreshed = await refreshOnce()
    if (refreshed) {
      return apiFetch<T>(path, { ...options, skipAuthRetry: true })
    }
    useAuthStore.getState().clearAuth()
    throw new ApiError(401, translate(useLocaleStore.getState().locale, 'session.expired'))
  }

  if (!response.ok) {
    let detail = response.statusText
    try {
      const errorBody = await response.json()
      detail = errorBody.detail ?? detail
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  login: (email: string, password: string) =>
    apiFetch<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: { email, password },
      skipAuthRetry: true,
    }),
  refresh: () => apiFetch<RefreshResponse>('/api/auth/refresh', { method: 'POST', skipAuthRetry: true }),
  logout: () => apiFetch<void>('/api/auth/logout', { method: 'POST', skipAuthRetry: true }),
  wsTicket: () => apiFetch<WsTicketResponse>('/api/auth/ws-ticket', { method: 'POST' }),
  listUsers: () => apiFetch<UserSummary[]>('/api/users'),
  createUser: (data: { email: string; password: string; role: Role }) =>
    apiFetch<UserSummary>('/api/users', { method: 'POST', body: data }),
  updateUserRole: (userId: string, role: Role) =>
    apiFetch<UserSummary>(`/api/users/${encodeURIComponent(userId)}/role`, {
      method: 'PATCH',
      body: { role },
    }),
  resetUserPassword: (userId: string, newPassword: string) =>
    apiFetch<void>(`/api/users/${encodeURIComponent(userId)}/reset-password`, {
      method: 'POST',
      body: { new_password: newPassword },
    }),
  deleteUser: (userId: string) =>
    apiFetch<void>(`/api/users/${encodeURIComponent(userId)}`, { method: 'DELETE' }),
}

export async function downloadExport(
  range: string,
  format: 'csv' | 'json',
  blockedOnly: boolean,
): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(
    buildUrl('/api/export', { range, format, blocked_only: blockedOnly }),
    {
      credentials: 'include',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    },
  )
  if (!response.ok) {
    throw new ApiError(response.status, 'Export failed. Check your permissions and try again.')
  }
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = `squid-events-${range}.${format}`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}
