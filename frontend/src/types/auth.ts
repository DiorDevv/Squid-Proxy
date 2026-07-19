export type Role = 'admin' | 'viewer'

export interface LoginResponse {
  access_token: string
  token_type: string
  expires_in_seconds: number
  role: Role
  email: string
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
