export type Role = 'admin' | 'viewer'

export interface LoginResponse {
  // Absent (undefined/null) exactly when mfa_required is true -- the
  // password was right but a TOTP code is still needed via
  // api.verifyMfa(challenge_token, code) before these are ever populated.
  access_token: string | null
  token_type: string
  expires_in_seconds: number | null
  role: Role | null
  email: string | null
  // null = unrestricted (every user before branch-scoping existed); set to
  // one branch tag to restrict this account to only that branch's data.
  branch: string | null
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
