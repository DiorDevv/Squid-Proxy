import { Inbox } from 'lucide-react'
import { useTranslation } from '@/i18n'

interface EmptyStateProps {
  message?: string
}

export function EmptyState({ message }: EmptyStateProps) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-col items-center justify-center gap-2 py-12 text-center">
      <Inbox className="h-6 w-6 text-muted-foreground" aria-hidden="true" />
      <p className="text-sm text-muted-foreground">{message ?? t('common.emptyDefault')}</p>
    </div>
  )
}
