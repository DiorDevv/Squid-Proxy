import { useQuery } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { AuditLogEntry, Page } from '@/types/api'

export function useAuditLog(limit: number, offset: number) {
  return useQuery({
    queryKey: ['audit-log', limit, offset],
    queryFn: () => apiFetch<Page<AuditLogEntry>>('/api/audit-log', { searchParams: { limit, offset } }),
    placeholderData: (previous) => previous,
  })
}
