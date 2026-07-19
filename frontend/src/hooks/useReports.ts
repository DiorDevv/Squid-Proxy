import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiFetch } from '@/lib/api-client'
import type { ReportStatus } from '@/types/api'

const REPORT_STATUS_QUERY_KEY = ['report-status']

export function useReportStatus() {
  return useQuery({
    queryKey: REPORT_STATUS_QUERY_KEY,
    queryFn: () => apiFetch<ReportStatus>('/api/reports/status'),
  })
}

interface SendReportNowResponse {
  sent: boolean
  since: string
  until: string
}

export function useSendReportNow() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: () => apiFetch<SendReportNowResponse>('/api/reports/send-now', { method: 'POST' }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: REPORT_STATUS_QUERY_KEY }),
  })
}
