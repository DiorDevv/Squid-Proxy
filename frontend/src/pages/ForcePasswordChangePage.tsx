import { KeyRound, LogOut } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { ChangePasswordForm } from '@/components/account/ChangePasswordForm'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/lib/auth-store'
import { useTranslation } from '@/i18n'

/** Shown instead of the whole app (see ProtectedRoute) while the account
 * is on the temporary password an admin issued -- the backend refuses
 * every other call until it's changed. */
export default function ForcePasswordChangePage() {
  const { t } = useTranslation()
  const { username, logout } = useAuth()
  const setMustChangePassword = useAuthStore((state) => state.setMustChangePassword)
  const navigate = useNavigate()

  async function handleLogout() {
    await logout()
    navigate('/login', { replace: true })
  }

  return (
    <div className="flex min-h-svh items-center justify-center bg-background p-4">
      <div className="flex w-full max-w-md flex-col gap-6 rounded-lg border border-border bg-card p-6 shadow-sm">
        <div className="flex flex-col gap-2">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-primary/15 text-primary">
            <KeyRound className="h-5 w-5" aria-hidden="true" />
          </span>
          <h1 className="text-lg font-semibold text-foreground">
            {t('passwordChange.forcedTitle')}
          </h1>
          <p className="text-sm text-muted-foreground">
            {t('passwordChange.forcedDescription', { username: username ?? '' })}
          </p>
        </div>
        <ChangePasswordForm
          username={username ?? ''}
          currentLabel={t('passwordChange.temporary')}
          onChanged={() => {
            setMustChangePassword(false)
            toast.success(t('passwordChange.success'))
          }}
        />
        <Button variant="ghost" size="sm" className="self-start gap-1.5" onClick={handleLogout}>
          <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
          {t('account.signOut')}
        </Button>
      </div>
    </div>
  )
}
