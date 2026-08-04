export type Role = 'admin' | 'viewer'

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in_seconds: number
  role: Role
  email: string
  // null = unrestricted (every user before branch-scoping existed); set to
  // one branch tag to restrict this account to only that branch's data.
  branch: string | null
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
