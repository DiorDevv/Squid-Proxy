import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

const TOTP_STATUS_QUERY_KEY = ['totp-status']

export function useTotpStatus() {
  return useQuery({
    queryKey: TOTP_STATUS_QUERY_KEY,
    queryFn: () => api.totpStatus(),
  })
}

export function useTotpSetup() {
  return useMutation({
    mutationFn: () => api.totpSetup(),
  })
}

export function useTotpConfirm() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (code: string) => api.totpConfirm(code),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TOTP_STATUS_QUERY_KEY }),
  })
}

export function useTotpDisable() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (password: string) => api.totpDisable(password),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: TOTP_STATUS_QUERY_KEY }),
  })
}
