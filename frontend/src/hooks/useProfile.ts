import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'

const ME_QUERY_KEY = ['auth', 'me']
const MY_SESSIONS_QUERY_KEY = ['auth', 'sessions']

export function useMe() {
  return useQuery({ queryKey: ME_QUERY_KEY, queryFn: () => api.me() })
}

export function useMySessions() {
  return useQuery({ queryKey: MY_SESSIONS_QUERY_KEY, queryFn: () => api.mySessions() })
}

export function useRevokeMySessions() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (sessionId?: string) => api.revokeMySessions(sessionId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: MY_SESSIONS_QUERY_KEY }),
  })
}

export function useChangePassword() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: ({
      currentPassword,
      newPassword,
    }: {
      currentPassword: string
      newPassword: string
    }) => api.changePassword(currentPassword, newPassword),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ME_QUERY_KEY })
      queryClient.invalidateQueries({ queryKey: MY_SESSIONS_QUERY_KEY })
    },
  })
}
