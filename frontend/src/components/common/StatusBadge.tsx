import { CircleCheck, CircleX } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'

interface StatusBadgeProps {
  blocked: boolean
}

/** Conveys status via icon + text, not color alone, per accessibility
 * requirements (colorblind-safe). */
export function StatusBadge({ blocked }: StatusBadgeProps) {
  const { t } = useTranslation()
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-xs font-medium',
        blocked ? 'bg-warning/15 text-warning' : 'bg-success/15 text-success',
      )}
    >
      {blocked ? (
        <CircleX className="h-3 w-3" aria-hidden="true" />
      ) : (
        <CircleCheck className="h-3 w-3" aria-hidden="true" />
      )}
      {blocked ? t('status.blocked') : t('status.allowed')}
    </span>
  )
}
