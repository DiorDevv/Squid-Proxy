import { useEffect, useState } from 'react'
import { toast } from 'sonner'
import type { UseQueryResult } from '@tanstack/react-query'
import { Button } from '@/components/ui/button'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { TelegramLinkCodeOut, TelegramLinkStatusOut } from '@/types/api'

type Translate = (key: TranslationKey, vars?: Record<string, string | number>) => string

interface TelegramLinkDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
  title: string
  instructions: string
  // Owned by the caller (see hooks/useTelegramLink.ts's useTelegramLinkFlow)
  // rather than fetched here -- see the module docstring below for why.
  code: TelegramLinkCodeOut | null
  onRequestNewCode: () => void
  useStatus: (code: string | null) => UseQueryResult<TelegramLinkStatusOut>
  onLinked: () => void
}

function secondsUntil(isoTimestamp: string): number {
  return Math.max(0, Math.round((new Date(isoTimestamp).getTime() - Date.now()) / 1000))
}

function formatMmSs(totalSeconds: number): string {
  const minutes = Math.floor(totalSeconds / 60)
  const seconds = totalSeconds % 60
  return `${minutes}:${String(seconds).padStart(2, '0')}`
}

/** Shared "show a 6-digit code with a countdown, poll until redeemed"
 * dialog for both a branch's own Telegram chat (AlertSettingsPanel) and
 * the global super-admin chat (SuperAdminTelegramPanel). Deliberately has
 * no data-fetching effect of its own -- `code` arrives as a prop, already
 * created by useTelegramLinkFlow's connect()/requestNewCode() (real event
 * handlers), so nothing here needs to synchronize local state from `open`
 * changing. The one effect this component does own (below) only ever
 * calls setState from inside a timer/query callback, never synchronously
 * in the effect body -- same shape as LoginPage.tsx's retryIn countdown. */
export function TelegramLinkDialog({
  open,
  onOpenChange,
  title,
  instructions,
  code,
  onRequestNewCode,
  useStatus,
  onLinked,
}: TelegramLinkDialogProps) {
  const { t } = useTranslation()
  const status = useStatus(code?.code ?? null)

  useEffect(() => {
    if (status.data?.consumed) {
      toast.success(t('settings.telegramLink.linkedSuccess'))
      onLinked()
      onOpenChange(false)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status.data?.consumed])

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{instructions}</DialogDescription>
        </DialogHeader>

        {code ? (
          <CodeCountdown key={code.expires_at} code={code} onRequestNewCode={onRequestNewCode} t={t} />
        ) : (
          <div className="flex flex-col items-center gap-2 py-4">
            <Skeleton className="h-12 w-40" />
          </div>
        )}

        <DialogFooter>
          <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>
            {t('settings.telegramLink.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** Keyed by `code.expires_at` in the parent, so every newly issued code
 * (including "get a new code" after expiry) remounts this with a fresh
 * `secondsLeft` derived once at mount -- the ticking effect below then
 * only ever decrements via a functional update inside setInterval's
 * callback, never re-deriving the absolute value from `code` itself. */
function CodeCountdown({
  code,
  onRequestNewCode,
  t,
}: {
  code: TelegramLinkCodeOut
  onRequestNewCode: () => void
  t: Translate
}) {
  const [secondsLeft, setSecondsLeft] = useState(() => secondsUntil(code.expires_at))

  useEffect(() => {
    const timer = window.setInterval(() => {
      setSecondsLeft((prev) => Math.max(0, prev - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [])

  if (secondsLeft <= 0) {
    return (
      <div className="flex flex-col items-center gap-3 py-4">
        <p className="text-sm text-destructive">{t('settings.telegramLink.codeExpired')}</p>
        <Button type="button" variant="outline" onClick={onRequestNewCode}>
          {t('settings.telegramLink.newCode')}
        </Button>
      </div>
    )
  }

  return (
    <div className="flex flex-col items-center gap-2 py-4">
      <span className="font-data text-4xl font-semibold tracking-[0.3em] text-foreground">{code.code}</span>
      <span className="text-sm text-muted-foreground">
        {t('settings.telegramLink.expiresIn', { time: formatMmSs(secondsLeft) })}
      </span>
    </div>
  )
}
