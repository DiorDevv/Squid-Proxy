import { API_BASE_URL } from '@/lib/constants'
import { decodeAccessTokenBranch, decodeAccessTokenRole, getAccessToken, useAuthStore } from '@/lib/auth-store'
import { requestReauth } from '@/lib/reauth-store'
import { translate, useLocaleStore } from '@/i18n'
import type {
  LoginResponse,
  MeResponse,
  RefreshResponse,
  Role,
  SessionInfo,
  TotpConfirmResponse,
  TotpSetupResponse,
  TotpStatusResponse,
  WsTicketResponse,
} from '@/types/auth'
import type {
  DomainCategoryImportResponse,
  DomainCategoryLabel,
  ExportJob,
  ExportManifest,
  ExportShareLink,
  UserSummary,
  UserWithTemporaryPassword,
} from '@/types/api'

// Exact machine-readable 403 details from backend api/deps.py.
const PASSWORD_CHANGE_REQUIRED = 'password_change_required'
const REAUTH_REQUIRED = 'reauth_required'

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
    // The refresh response carries nothing but the token, so role is
    // recovered from the token itself rather than from profile state that
    // may not be loaded yet -- a session restored via a hard reload must
    // still be able to silently refresh past its first access-token expiry.
    const role = decodeAccessTokenRole(body.access_token)
    if (!role) return false
    useAuthStore.getState().setAccessToken(body.access_token, role, decodeAccessTokenBranch(body.access_token))
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
  skipReauth?: boolean
}

export async function apiFetch<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { method = 'GET', body, searchParams, skipAuthRetry, skipReauth } = options
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
      // FastAPI's own errors use "detail"; slowapi's rate-limit handler
      // (429 responses) uses "error" instead -- check both rather than
      // silently falling back to the generic HTTP status text.
      detail = errorBody.detail ?? errorBody.error ?? detail
    } catch {
      // response had no JSON body
    }
    const locale = useLocaleStore.getState().locale
    if (response.status === 403 && detail === REAUTH_REQUIRED && !skipReauth) {
      if (await requestReauth()) {
        return apiFetch<T>(path, { ...options, skipReauth: true })
      }
      throw new ApiError(403, translate(locale, 'reauth.cancelled'))
    }
    if (response.status === 403 && detail === PASSWORD_CHANGE_REQUIRED) {
      useAuthStore.getState().setMustChangePassword(true)
      throw new ApiError(403, translate(locale, 'passwordChange.required'))
    }
    throw new ApiError(response.status, detail)
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  login: (username: string, password: string) =>
    apiFetch<LoginResponse>('/api/auth/login', {
      method: 'POST',
      body: { username, password },
      skipAuthRetry: true,
    }),
  refresh: () => apiFetch<RefreshResponse>('/api/auth/refresh', { method: 'POST', skipAuthRetry: true }),
  logout: () => apiFetch<void>('/api/auth/logout', { method: 'POST', skipAuthRetry: true }),
  wsTicket: () => apiFetch<WsTicketResponse>('/api/auth/ws-ticket', { method: 'POST' }),
  me: () => apiFetch<MeResponse>('/api/auth/me'),
  reauth: (password: string) =>
    apiFetch<{ valid_minutes: number }>('/api/auth/reauth', { method: 'POST', body: { password } }),
  changePassword: (currentPassword: string, newPassword: string) =>
    apiFetch<{ sessions_closed: number }>('/api/auth/password', {
      method: 'POST',
      body: { current_password: currentPassword, new_password: newPassword },
    }),
  mySessions: () => apiFetch<SessionInfo[]>('/api/auth/sessions'),
  revokeMySessions: (sessionId?: string) =>
    apiFetch<{ closed: number }>('/api/auth/sessions', {
      method: 'DELETE',
      searchParams: { session_id: sessionId },
    }),
  verifyMfa: (challengeToken: string, code: string) =>
    apiFetch<LoginResponse>('/api/auth/login/verify-mfa', {
      method: 'POST',
      body: { challenge_token: challengeToken, code },
      skipAuthRetry: true,
    }),
  totpStatus: () => apiFetch<TotpStatusResponse>('/api/auth/totp/status'),
  totpSetup: () => apiFetch<TotpSetupResponse>('/api/auth/totp/setup', { method: 'POST' }),
  totpConfirm: (code: string) =>
    apiFetch<TotpConfirmResponse>('/api/auth/totp/confirm', { method: 'POST', body: { code } }),
  totpDisable: (password: string) =>
    apiFetch<void>('/api/auth/totp/disable', { method: 'POST', body: { password } }),
  listUsers: () => apiFetch<UserSummary[]>('/api/users'),
  createUser: (data: {
    username: string
    full_name: string
    note: string | null
    email: string | null
    role: Role
    branch: string | null
  }) => apiFetch<UserWithTemporaryPassword>('/api/users', { method: 'POST', body: data }),
  updateUserProfile: (
    userId: string,
    data: { full_name?: string; note?: string | null; email?: string | null },
  ) => apiFetch<UserSummary>(`/api/users/${encodeURIComponent(userId)}`, { method: 'PATCH', body: data }),
  updateUserRole: (userId: string, role: Role) =>
    apiFetch<UserSummary>(`/api/users/${encodeURIComponent(userId)}/role`, {
      method: 'PATCH',
      body: { role },
    }),
  updateUserBranch: (userId: string, branch: string | null) =>
    apiFetch<UserSummary>(`/api/users/${encodeURIComponent(userId)}/branch`, {
      method: 'PATCH',
      body: { branch },
    }),
  resetUserPassword: (userId: string) =>
    apiFetch<UserWithTemporaryPassword>(`/api/users/${encodeURIComponent(userId)}/reset-password`, {
      method: 'POST',
    }),
  setUserActive: (userId: string, active: boolean) =>
    apiFetch<UserSummary>(`/api/users/${encodeURIComponent(userId)}/active`, {
      method: 'POST',
      body: { active },
    }),
  unlockUser: (userId: string) =>
    apiFetch<UserSummary>(`/api/users/${encodeURIComponent(userId)}/unlock`, { method: 'POST' }),
  resetUserTotp: (userId: string) =>
    apiFetch<UserSummary>(`/api/users/${encodeURIComponent(userId)}/reset-2fa`, { method: 'POST' }),
  userSessions: (userId: string) =>
    apiFetch<SessionInfo[]>(`/api/users/${encodeURIComponent(userId)}/sessions`),
  revokeUserSessions: (userId: string, sessionId?: string) =>
    apiFetch<{ closed: number }>(`/api/users/${encodeURIComponent(userId)}/sessions`, {
      method: 'DELETE',
      searchParams: { session_id: sessionId },
    }),
  createExportJob: (params: {
    range?: string
    fromTs?: string
    toTs?: string
    format: 'csv' | 'json' | 'xlsx'
    blockedOnly: boolean
    branch?: string | null
    clientIp?: string | null
    domain?: string | null
    category?: DomainCategoryLabel | null
    columns?: string[] | null
  }) =>
    apiFetch<ExportJob>('/api/export/jobs', {
      method: 'POST',
      searchParams: {
        range: params.range,
        from_ts: params.fromTs,
        to_ts: params.toTs,
        format: params.format,
        blocked_only: params.blockedOnly,
        branch: params.branch ?? undefined,
        client_ip: params.clientIp ?? undefined,
        domain: params.domain ?? undefined,
        category: params.category ?? undefined,
        // Same comma-separated shape ExportJob.columns is stored/parsed as
        // server-side (see export_job_service.create_job /
        // api/routes/export.py's _parse_columns) -- omitted entirely (not
        // an empty string) when every column is wanted, so the backend's
        // own "None means all" default applies rather than a 400 from an
        // empty column list.
        columns: params.columns && params.columns.length > 0 ? params.columns.join(',') : undefined,
      },
    }),
  getExportJob: (jobId: string) => apiFetch<ExportJob>(`/api/export/jobs/${encodeURIComponent(jobId)}`),
  listExportJobs: () => apiFetch<ExportJob[]>('/api/export/jobs'),
  cancelExportJob: (jobId: string) =>
    apiFetch<ExportJob>(`/api/export/jobs/${encodeURIComponent(jobId)}/cancel`, { method: 'POST' }),
  createExportShareLink: (jobId: string) =>
    apiFetch<ExportShareLink>(`/api/export/jobs/${encodeURIComponent(jobId)}/share`, { method: 'POST' }),
  revokeExportShareLink: (jobId: string) =>
    apiFetch<ExportJob>(`/api/export/jobs/${encodeURIComponent(jobId)}/share/revoke`, { method: 'POST' }),
}

/** Downloads every current domain-category override as a CSV file --
 * mirrors downloadExportJob's blob-download approach (an authenticated
 * binary response can't just be an <a href>). */
export async function downloadDomainCategoriesExport(): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(buildUrl('/api/domain-categories/export'), {
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new ApiError(response.status, 'Export failed. Check your permissions and try again.')
  }
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = 'domain_categories.csv'
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

/** Downloads the whole "Who" list (every page, same filters/sort) as an
 * Excel or CSV file -- admin/auditor only and audited on the backend. */
export async function downloadActorList(
  format: 'xlsx' | 'csv',
  params: Record<string, string | number | undefined>,
): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(buildUrl('/api/analytics/actors/export', { ...params, format }), {
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new ApiError(response.status, 'Export failed. Check your permissions and try again.')
  }
  const disposition = response.headers.get('Content-Disposition')
  const filename = disposition?.match(/filename="([^"]+)"/)?.[1] ?? `kim.${format}`
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

/** Downloads the whole blocked-domain list (every page, same filters) --
 * Excel, CSV, or with columns='domain' a header-less CSV of domain names
 * only. Admin/auditor only and audited on the backend. */
export async function downloadBlockedDomains(
  format: 'xlsx' | 'csv',
  params: Record<string, string | number | undefined>,
): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(buildUrl('/api/blocked-domains/export', { ...params, format }), {
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new ApiError(response.status, 'Export failed. Check your permissions and try again.')
  }
  const disposition = response.headers.get('Content-Disposition')
  const filename = disposition?.match(/filename="([^"]+)"/)?.[1] ?? `bloklangan-domenlar.${format}`
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

/** Uploads a `domain,category` CSV to bulk-apply category overrides -- a
 * multipart file upload, so it can't go through apiFetch (which always
 * JSON-encodes its body). Each row is applied independently server-side;
 * see the returned response's `errors` for any rows that were skipped. */
export async function importDomainCategories(file: File): Promise<DomainCategoryImportResponse> {
  const token = getAccessToken()
  const formData = new FormData()
  formData.append('file', file)
  const response = await fetch(buildUrl('/api/domain-categories/import'), {
    method: 'POST',
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: formData,
  })
  if (!response.ok) {
    let detail = response.statusText
    try {
      const errorBody = await response.json()
      detail = errorBody.detail ?? errorBody.error ?? detail
    } catch {
      // response had no JSON body
    }
    throw new ApiError(response.status, detail)
  }
  return (await response.json()) as DomainCategoryImportResponse
}

/** Downloads a finished background export job's result file (see
 * api.createExportJob / useExportJob) for GET /api/export/jobs/{id}/download
 * -- an authenticated binary response, so it can't just be an <a href>;
 * fetch it and hand the browser a blob URL instead. The plain synchronous
 * GET /api/export this replaced in the UI still exists server-side for
 * scripted/curl use. */
export async function downloadExportJob(jobId: string): Promise<void> {
  const token = getAccessToken()
  const response = await fetch(buildUrl(`/api/export/jobs/${jobId}/download`), {
    credentials: 'include',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
  if (!response.ok) {
    throw new ApiError(response.status, 'Export failed. Check your permissions and try again.')
  }
  const disposition = response.headers.get('Content-Disposition')
  const filename = disposition?.match(/filename="([^"]+)"/)?.[1] ?? 'export'
  const blob = await response.blob()
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = filename
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

/** Downloads GET /api/subject-access/dossier as a .dossier.json file --
 * everything this deployment currently knows about one client IP or user,
 * signed the same way an export manifest is (see downloadExportManifest,
 * scripts/verify_export.py's signature-check logic applies to this JSON
 * body too). Admin-only on the backend; every call is audited there. */
export async function downloadSubjectDossier(
  subjectType: 'client_ip' | 'user',
  value: string,
): Promise<void> {
  const dossier = await apiFetch<Record<string, unknown>>('/api/subject-access/dossier', {
    searchParams: { subject_type: subjectType, value },
  })
  const blob = new Blob([JSON.stringify(dossier, null, 2)], { type: 'application/json' })
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = `${subjectType}-${value}.dossier.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}

/** Downloads GET /api/export/jobs/{id}/manifest as a .manifest.json file --
 * hand this, alongside the export file itself, to whoever needs to verify
 * it later (offline, with scripts/verify_export.py; see that script and
 * ExportManifest). A plain JSON GET, but saved as a file (not just
 * returned) so the download UX matches downloadExportJob's. */
export async function downloadExportManifest(jobId: string): Promise<void> {
  const manifest = await apiFetch<ExportManifest>(`/api/export/jobs/${jobId}/manifest`)
  const blob = new Blob([JSON.stringify(manifest, null, 2)], { type: 'application/json' })
  const objectUrl = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = `${jobId}.manifest.json`
  document.body.appendChild(link)
  link.click()
  link.remove()
  URL.revokeObjectURL(objectUrl)
}
