export type Role = 'superadmin' | 'admin' | 'viewer' | 'auditor'

/** Feature permissions (backend core/permissions.py). */
export type Permission =
  | 'export'
  | 'raw_export'
  | 'watchlist'
  | 'reports'
  | 'subject_access'
  | 'categories'
  | 'alerts'
  | 'audit'

export interface LoginResponse {
  // Absent (undefined/null) exactly when mfa_required is true -- the
  // password was right but a TOTP code is still needed via
  // api.verifyMfa(challenge_token, code) before these are ever populated.
  access_token: string | null
  token_type: string
  expires_in_seconds: number | null
  role: Role | null
  username: string | null
  full_name: string | null
  email: string | null
  // True: signed in with an admin-issued temporary password -- every API
  // call but /me and /password answers 403 until it's changed.
  must_change_password: boolean
  // null = unrestricted (every user before branch-scoping existed); set to
  // one branch tag to restrict this account to only that branch's data.
  branch: string | null
  // [] = every branch; otherwise the branches this account is limited to.
  branches?: string[]
  // Effective feature permissions (see lib/permissions.ts).
  permissions?: Permission[]
  expires_at?: string | null
  mfa_required: boolean
  challenge_token: string | null
}

export interface RefreshResponse {
  access_token: string
  token_type: string
  expires_in_seconds: number
}

export interface WsTicketResponse {
  ticket: string
  expires_in_seconds: number
}

export interface TotpSetupResponse {
  secret: string
  otpauth_uri: string
}

export interface TotpConfirmResponse {
  recovery_codes: string[]
}

export interface TotpStatusResponse {
  enabled: boolean
}

export interface MeResponse {
  id: string
  username: string
  full_name: string
  email: string | null
  role: Role
  branch: string | null
  branches?: string[] | null
  permissions?: Permission[] | null
  expires_at?: string | null
  must_change_password: boolean
  totp_enabled: boolean
  password_changed_at: string | null
  last_login_at: string | null
}

export interface SessionInfo {
  id: string
  ip: string | null
  user_agent: string | null
  started_at: string | null
  last_seen_at: string | null
  expires_at: string
  current: boolean
}
