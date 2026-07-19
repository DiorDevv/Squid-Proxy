export interface LiveEvent {
  id: number
  timestamp: string
  client_ip: string
  action: string
  status_code: number
  method: string
  domain: string | null
  url: string
  user: string | null
  bytes: number
  blocked: boolean
}
