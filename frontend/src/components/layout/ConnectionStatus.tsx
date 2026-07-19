import { cn } from '@/lib/utils'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useTranslation } from '@/i18n'

export function ConnectionStatus() {
  const { t } = useTranslation()
  const { connectionState, pollingError } = useLiveEvents()

  const isLive = connectionState === 'open'
  const isDisconnected = !isLive && pollingError
  const label = isLive ? t('connection.live') : isDisconnected ? t('connection.disconnected') : t('connection.polling')

  return (
    <div
      className="flex items-center gap-2 rounded-md border border-border bg-secondary/50 px-2.5 py-1.5 text-xs"
      role="status"
      aria-live="polite"
    >
      <span className="relative flex h-2 w-2" aria-hidden="true">
        {isLive && (
          <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-success opacity-75" />
        )}
        <span
          className={cn(
            'relative inline-flex h-2 w-2 rounded-full',
            isLive && 'bg-success shadow-[0_0_6px_var(--success)]',
            !isLive && !isDisconnected && 'bg-muted-foreground',
            isDisconnected && 'bg-destructive',
          )}
        />
      </span>
      <span className="font-data text-muted-foreground">{label}</span>
    </div>
  )
}
