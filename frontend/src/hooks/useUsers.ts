import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { Role } from '@/types/auth'

const USERS_QUERY_KEY = ['users']

export function useUsers() {
  return useQuery({
    queryKey: USERS_QUERY_KEY,
    queryFn: () => api.listUsers(),
  })
}

/** Every user mutation refreshes the list -- they all change something the
 * table shows (status badges, session counts, role, ...). */
function useUserMutation<TVariables, TResult>(
  mutationFn: (variables: TVariables) => Promise<TResult>,
) {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: USERS_QUERY_KEY }),
  })
}

export function useCreateUser() {
  return useUserMutation(
    (data: {
      username: string
      full_name: string
      note: string | null
      email: string | null
      role: Role
      branch: string | null
    }) => api.createUser(data),
  )
}

export function useUpdateUserProfile() {
  return useUserMutation(
    ({
      userId,
      ...data
    }: {
      userId: string
      full_name?: string
      note?: string | null
      email?: string | null
    }) => api.updateUserProfile(userId, data),
  )
}

export function useUpdateUserRole() {
  return useUserMutation(({ userId, role }: { userId: string; role: Role }) =>
    api.updateUserRole(userId, role),
  )
}

export function useUpdateUserBranch() {
  return useUserMutation(({ userId, branch }: { userId: string; branch: string | null }) =>
    api.updateUserBranch(userId, branch),
  )
}

export function useResetUserPassword() {
  return useUserMutation((userId: string) => api.resetUserPassword(userId))
}

export function useSetUserActive() {
  return useUserMutation(({ userId, active }: { userId: string; active: boolean }) =>
    api.setUserActive(userId, active),
  )
}

export function useUnlockUser() {
  return useUserMutation((userId: string) => api.unlockUser(userId))
}

export function useResetUserTotp() {
  return useUserMutation((userId: string) => api.resetUserTotp(userId))
}

export function useUserSessions(userId: string | null) {
  return useQuery({
    queryKey: ['users', userId, 'sessions'],
    queryFn: () => api.userSessions(userId as string),
    enabled: userId !== null,
  })
}

export function useRevokeUserSessions() {
  return useUserMutation(({ userId, sessionId }: { userId: string; sessionId?: string }) =>
    api.revokeUserSessions(userId, sessionId),
  )
}
