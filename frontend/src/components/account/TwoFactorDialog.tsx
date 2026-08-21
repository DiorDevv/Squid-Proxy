import { useState } from 'react'
import { toast } from 'sonner'
import QRCode from 'qrcode'
import { Check, Copy, KeyRound, ShieldCheck, ShieldOff, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Skeleton } from '@/components/ui/skeleton'
import { useTotpConfirm, useTotpDisable, useTotpSetup, useTotpStatus } from '@/hooks/useTotp'
import { ApiError } from '@/lib/api-client'
import { useTranslation } from '@/i18n'

interface TwoFactorDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

// Only the steps a user reaches by taking an explicit action within the
// flow (never derivable from the server) -- null means "no in-progress
// sub-flow, just show whatever useTotpStatus says (loading/on/off)".
// Deriving the resting state at render time instead of syncing it into
// state via an effect sidesteps a whole class of stale-step bugs (and the
// cascading-render footgun effect-driven setState invites in the first
// place).
type SubStep = 'settingUp' | 'recoveryCodes' | 'disabling' | null

/** Self-service TOTP enable/disable for the signed-in account, reachable
 * from SidebarUserMenu -- any role can protect their own login this way,
 * not just admins (though that's who this matters most for). */
export function TwoFactorDialog({ open, onOpenChange }: TwoFactorDialogProps) {
  const { t } = useTranslation()
  const status = useTotpStatus()
  const setup = useTotpSetup()
  const confirm = useTotpConfirm()
  const disable = useTotpDisable()

  const [subStep, setSubStep] = useState<SubStep>(null)
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null)
  const [secret, setSecret] = useState('')
  const [code, setCode] = useState('')
  const [password, setPassword] = useState('')
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([])
  const [copied, setCopied] = useState(false)
  const [errorMessage, setErrorMessage] = useState<string | null>(null)

  const restingStep = status.isLoading ? 'loading' : status.data?.enabled ? 'on' : 'off'
  const step = subStep ?? restingStep

  // Reset every bit of in-flight form state as a direct response to the
  // dialog closing (a real event, not something to sync via an effect) --
  // otherwise reopening mid-setup would show stale step/code/error state
  // instead of starting fresh from whatever the server now says.
  function handleOpenChange(next: boolean) {
    if (!next) {
      setSubStep(null)
      setCode('')
      setPassword('')
      setErrorMessage(null)
      setCopied(false)
    }
    onOpenChange(next)
  }

  async function handleBeginSetup() {
    setErrorMessage(null)
    try {
      const result = await setup.mutateAsync()
      setSecret(result.secret)
      setQrDataUrl(await QRCode.toDataURL(result.otpauth_uri, { width: 220, margin: 1 }))
      setSubStep('settingUp')
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : t('common.errorDefault'))
    }
  }

  async function handleConfirm(e: React.FormEvent) {
    e.preventDefault()
    setErrorMessage(null)
    try {
      const result = await confirm.mutateAsync(code.trim())
      setRecoveryCodes(result.recovery_codes)
      setSubStep('recoveryCodes')
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : t('common.errorDefault'))
    }
  }

  async function handleDisable(e: React.FormEvent) {
    e.preventDefault()
    setErrorMessage(null)
    try {
      await disable.mutateAsync(password)
      toast.success(t('account.totpDisabledToast'))
      handleOpenChange(false)
    } catch (err) {
      setErrorMessage(err instanceof ApiError ? err.message : t('common.errorDefault'))
    }
  }

  function handleCopyRecoveryCodes() {
    void navigator.clipboard.writeText(recoveryCodes.join('\n'))
    setCopied(true)
  }

  function handleDoneWithRecoveryCodes() {
    toast.success(t('account.totpEnabledToast'))
    handleOpenChange(false)
  }

  return (
    <Dialog open={open} onOpenChange={handleOpenChange}>
      <DialogContent className={step === 'recoveryCodes' ? 'sm:max-w-md' : undefined}>
        {step === 'loading' && (
          <div className="flex flex-col gap-3 py-4">
            <Skeleton className="h-5 w-40" />
            <Skeleton className="h-4 w-64" />
            <Skeleton className="h-9 w-32" />
          </div>
        )}

        {step === 'off' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-muted-foreground" aria-hidden="true" />
                {t('account.totpTitle')}
              </DialogTitle>
              <DialogDescription>{t('account.totpOffDescription')}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button onClick={handleBeginSetup} disabled={setup.isPending}>
                {setup.isPending ? t('account.totpStarting') : t('account.totpEnable')}
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'settingUp' && (
          <form onSubmit={handleConfirm} className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>{t('account.totpSetupTitle')}</DialogTitle>
              <DialogDescription>{t('account.totpSetupDescription')}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col items-center gap-3">
              {qrDataUrl && (
                <img
                  src={qrDataUrl}
                  alt={t('account.totpQrAlt')}
                  className="h-[220px] w-[220px] rounded-md border border-border"
                />
              )}
              <div className="flex flex-col items-center gap-1">
                <span className="text-xs text-muted-foreground">{t('account.totpManualEntry')}</span>
                <span className="font-data rounded bg-secondary px-2 py-1 text-xs tracking-wider text-foreground">
                  {secret}
                </span>
              </div>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="totp-confirm-code">{t('account.totpCodeLabel')}</Label>
              <Input
                id="totp-confirm-code"
                autoComplete="one-time-code"
                autoFocus
                required
                value={code}
                onChange={(e) => setCode(e.target.value)}
                className="font-data text-center tracking-[0.3em]"
                placeholder="000000"
              />
            </div>
            {errorMessage && (
              <p className="flex items-center gap-1.5 text-xs text-destructive">
                <TriangleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {errorMessage}
              </p>
            )}
            <DialogFooter>
              <Button type="submit" disabled={confirm.isPending}>
                {confirm.isPending ? t('account.totpConfirming') : t('account.totpConfirm')}
              </Button>
            </DialogFooter>
          </form>
        )}

        {step === 'recoveryCodes' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <KeyRound className="h-4 w-4 text-warning" aria-hidden="true" />
                {t('account.totpRecoveryTitle')}
              </DialogTitle>
              <DialogDescription>{t('account.totpRecoveryDescription')}</DialogDescription>
            </DialogHeader>
            <div className="grid grid-cols-2 gap-2 rounded-md border border-border bg-secondary/40 p-3">
              {recoveryCodes.map((rc) => (
                <span key={rc} className="font-data text-center text-xs text-foreground">
                  {rc}
                </span>
              ))}
            </div>
            <Button variant="outline" size="sm" className="gap-1.5" onClick={handleCopyRecoveryCodes}>
              {copied ? (
                <Check className="h-3.5 w-3.5" aria-hidden="true" />
              ) : (
                <Copy className="h-3.5 w-3.5" aria-hidden="true" />
              )}
              {copied ? t('account.totpCopied') : t('account.totpCopyAll')}
            </Button>
            <DialogFooter>
              <Button onClick={handleDoneWithRecoveryCodes}>{t('account.totpDone')}</Button>
            </DialogFooter>
          </>
        )}

        {step === 'on' && (
          <>
            <DialogHeader>
              <DialogTitle className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-success" aria-hidden="true" />
                {t('account.totpTitle')}
              </DialogTitle>
              <DialogDescription>{t('account.totpOnDescription')}</DialogDescription>
            </DialogHeader>
            <DialogFooter>
              <Button variant="destructive" onClick={() => setSubStep('disabling')} className="gap-1.5">
                <ShieldOff className="h-4 w-4" aria-hidden="true" />
                {t('account.totpDisable')}
              </Button>
            </DialogFooter>
          </>
        )}

        {step === 'disabling' && (
          <form onSubmit={handleDisable} className="flex flex-col gap-4">
            <DialogHeader>
              <DialogTitle>{t('account.totpDisableTitle')}</DialogTitle>
              <DialogDescription>{t('account.totpDisableDescription')}</DialogDescription>
            </DialogHeader>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="totp-disable-password">{t('account.totpPasswordLabel')}</Label>
              <Input
                id="totp-disable-password"
                type="password"
                autoComplete="current-password"
                autoFocus
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
            </div>
            {errorMessage && (
              <p className="flex items-center gap-1.5 text-xs text-destructive">
                <TriangleAlert className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
                {errorMessage}
              </p>
            )}
            <DialogFooter>
              <Button type="submit" variant="destructive" disabled={disable.isPending}>
                {disable.isPending ? t('account.totpDisabling') : t('account.totpDisableConfirm')}
              </Button>
            </DialogFooter>
          </form>
        )}
      </DialogContent>
    </Dialog>
  )
}
