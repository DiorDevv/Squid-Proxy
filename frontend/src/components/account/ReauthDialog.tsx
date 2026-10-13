import { useState } from 'react'
import { ShieldCheck } from 'lucide-react'
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
import { ApiError, api } from '@/lib/api-client'
import { useReauthStore } from '@/lib/reauth-store'
import { useTranslation } from '@/i18n'

/** Mounted once (App.tsx). Opened by apiFetch whenever a sensitive call
 * comes back 403 "reauth_required" -- see lib/reauth-store.ts. */
export function ReauthDialog() {
  const { t } = useTranslation()
  const open = useReauthStore((state) => state.open)
  const settle = useReauthStore((state) => state.settle)
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  function finish(confirmed: boolean) {
    setPassword('')
    setError(null)
    settle(confirmed)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setSubmitting(true)
    setError(null)
    try {
      // skipReauth isn't needed: /reauth itself never answers reauth_required.
      await api.reauth(password)
      finish(true)
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('reauth.error'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && finish(false)}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <ShieldCheck className="h-4 w-4 text-primary" aria-hidden="true" />
              {t('reauth.title')}
            </DialogTitle>
            <DialogDescription>{t('reauth.description')}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reauth-password">{t('reauth.passwordLabel')}</Label>
            <Input
              id="reauth-password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              aria-invalid={error !== null}
              autoFocus
            />
            {error && (
              <p role="alert" className="text-xs text-destructive">
                {error}
              </p>
            )}
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={() => finish(false)}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={submitting || password.length === 0}>
              {submitting ? t('reauth.confirming') : t('reauth.confirm')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
