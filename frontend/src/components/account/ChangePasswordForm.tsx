import { useState } from 'react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { PasswordChecklist } from '@/components/account/PasswordChecklist'
import { useChangePassword } from '@/hooks/useProfile'
import { ApiError } from '@/lib/api-client'
import { PASSWORD_HISTORY, passwordAcceptable } from '@/lib/password-policy'
import { useTranslation } from '@/i18n'

interface ChangePasswordFormProps {
  username: string
  /** Label for the current-password field -- "Temporary password" on the
   * forced first-login screen. */
  currentLabel?: string
  onChanged: (sessionsClosed: number) => void
}

export function ChangePasswordForm({ username, currentLabel, onChanged }: ChangePasswordFormProps) {
  const { t } = useTranslation()
  const changePassword = useChangePassword()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [error, setError] = useState<string | null>(null)

  const mismatch = confirmPassword.length > 0 && confirmPassword !== newPassword
  const canSubmit =
    currentPassword.length > 0 &&
    passwordAcceptable(newPassword, username) &&
    newPassword === confirmPassword &&
    !changePassword.isPending

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    changePassword.mutate(
      { currentPassword, newPassword },
      {
        onSuccess: (result) => {
          setCurrentPassword('')
          setNewPassword('')
          setConfirmPassword('')
          onChanged(result.sessions_closed)
        },
        onError: (err) =>
          setError(err instanceof ApiError ? err.message : t('passwordChange.error')),
      },
    )
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="current-password">{currentLabel ?? t('passwordChange.current')}</Label>
        <Input
          id="current-password"
          type="password"
          autoComplete="current-password"
          required
          value={currentPassword}
          onChange={(e) => setCurrentPassword(e.target.value)}
        />
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="new-password">{t('passwordChange.new')}</Label>
        <Input
          id="new-password"
          type="password"
          autoComplete="new-password"
          required
          value={newPassword}
          onChange={(e) => setNewPassword(e.target.value)}
        />
        <PasswordChecklist password={newPassword} username={username} />
        <p className="text-xs text-muted-foreground">
          {t('passwordPolicy.history', { count: PASSWORD_HISTORY })}
        </p>
      </div>
      <div className="flex flex-col gap-1.5">
        <Label htmlFor="confirm-password">{t('passwordChange.confirm')}</Label>
        <Input
          id="confirm-password"
          type="password"
          autoComplete="new-password"
          required
          value={confirmPassword}
          onChange={(e) => setConfirmPassword(e.target.value)}
          aria-invalid={mismatch}
        />
        {mismatch && <p className="text-xs text-destructive">{t('passwordChange.mismatch')}</p>}
      </div>
      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}
      <div>
        <Button type="submit" disabled={!canSubmit}>
          {changePassword.isPending ? t('passwordChange.saving') : t('passwordChange.submit')}
        </Button>
      </div>
    </form>
  )
}
