import { TriangleAlert } from 'lucide-react'
import { useHealthCheck } from '@/hooks/useHealthCheck'
import { useTranslation } from '@/i18n'

const HIGH_FAILURE_THRESHOLD = 0.5

export function LogHealthBanner() {
  const { t } = useTranslation()
  const { data } = useHealthCheck()

  if (!data) return null

  const hasTraffic = data.log_lines_seen > 0
  const highFailureRate =
    hasTraffic && data.log_parse_failure_rate !== null && data.log_parse_failure_rate >= HIGH_FAILURE_THRESHOLD
  const tailerDown = !data.log_tailer_alive
  const hasUnarchivedPurge = data.unarchived_purge_branches.length > 0

  if (!highFailureRate && !tailerDown && !hasUnarchivedPurge) return null

  const message = highFailureRate
    ? t('health.parseFailure', { rate: Math.round(data.log_parse_failure_rate! * 100) })
    : tailerDown
      ? t('health.tailerDown')
      : t('health.unarchivedPurge', { branches: data.unarchived_purge_branches.join(', ') })

  return (
    <div
      className="flex items-center gap-2 border-b border-destructive/30 bg-destructive/10 px-4 py-2 text-sm text-destructive md:px-6"
      role="alert"
    >
      <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span>{message}</span>
    </div>
  )
}
