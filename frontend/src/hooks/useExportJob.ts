import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api-client'
import type { DomainCategoryLabel, ExportJob } from '@/types/api'

const ACTIVE_STATUSES = new Set<ExportJob['status']>(['pending', 'running'])
const POLL_INTERVAL_MS = 2_000
const EXPORT_JOBS_QUERY_KEY = ['export-jobs']

interface CreateExportJobParams {
  range?: string
  fromTs?: string
  toTs?: string
  format: 'csv' | 'json' | 'xlsx'
  blockedOnly: boolean
  branch?: string | null
  clientIp?: string | null
  domain?: string | null
  category?: DomainCategoryLabel | null
  columns?: string[] | null
}

export function useCreateExportJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (params: CreateExportJobParams) => api.createExportJob(params),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: EXPORT_JOBS_QUERY_KEY }),
  })
}

/** Polls GET /api/export/jobs/{id} while the job is pending/running, and
 * stops once it lands on done/failed/cancelled -- jobId is null when
 * nothing's in flight, which disables the query entirely. */
export function useExportJob(jobId: string | null) {
  return useQuery({
    queryKey: ['export-job', jobId],
    queryFn: () => api.getExportJob(jobId!),
    enabled: jobId !== null,
    refetchInterval: (query) => (ACTIVE_STATUSES.has(query.state.data?.status as ExportJob['status']) ? POLL_INTERVAL_MS : false),
  })
}

/** POST /api/export/jobs/{id}/cancel is asynchronous (see the route's
 * docstring) -- it doesn't itself change what the UI shows, so this just
 * invalidates the tracked job's query to pull the still-PENDING/RUNNING
 * response immediately rather than waiting for the next 2s poll tick; the
 * poll after that is what actually observes CANCELLED landing. */
export function useCancelExportJob() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => api.cancelExportJob(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['export-job', jobId] })
      queryClient.invalidateQueries({ queryKey: EXPORT_JOBS_QUERY_KEY })
    },
  })
}

/** Backs the "recent exports" list (see components/settings/ExportJobsPanel)
 * -- GET /api/export/jobs already returns everyone's last 20 jobs (single
 * shared admin role, no per-user scoping elsewhere in this app either), so
 * this alone gives full visibility into what's running/queued/done without
 * needing to track individual job ids. Polls at the same slower cadence as
 * the rest of the app's "live" panels; useExportJob's own faster 2s poll on
 * whichever job the current session just started (and the invalidation in
 * useCreateExportJob above) covers the responsiveness that matters more. */
export function useExportJobs() {
  return useQuery({
    queryKey: EXPORT_JOBS_QUERY_KEY,
    queryFn: () => api.listExportJobs(),
    refetchInterval: POLL_INTERVAL_MS * 5,
  })
}

/** Issues a fresh share link for a DONE job (see ExportJobsPanel) --
 * invalidates both the single-job and list queries since share_link_active/
 * share_link_expires_at on the job row change as a side effect (see
 * export_job_service.create_share_link), even though the raw token itself
 * (this mutation's actual return value) is never stored in either cache. */
export function useCreateExportShareLink() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => api.createExportShareLink(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['export-job', jobId] })
      queryClient.invalidateQueries({ queryKey: EXPORT_JOBS_QUERY_KEY })
    },
  })
}

export function useRevokeExportShareLink() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (jobId: string) => api.revokeExportShareLink(jobId),
    onSuccess: (_, jobId) => {
      queryClient.invalidateQueries({ queryKey: ['export-job', jobId] })
      queryClient.invalidateQueries({ queryKey: EXPORT_JOBS_QUERY_KEY })
    },
  })
}
