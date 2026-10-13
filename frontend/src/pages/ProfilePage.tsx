import { useState } from 'react'
import { toast } from 'sonner'
import { ShieldCheck, ShieldOff } from 'lucide-react'
import { Panel } from '@/components/common/Panel'
import { ErrorState } from '@/components/common/ErrorState'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { ChangePasswordForm } from '@/components/account/ChangePasswordForm'
import { SessionsTable } from '@/components/account/SessionsTable'
import { TwoFactorDialog } from '@/components/account/TwoFactorDialog'
import { useMe, useMySessions, useRevokeMySessions } from '@/hooks/useProfile'
import { ApiError } from '@/lib/api-client'
import { formatDateTime } from '@/lib/format'
import { ROLE_LABEL_KEYS } from '@/lib/roles'
import { useTranslation } from '@/i18n'

/** "My profile": who I am, my password, my 2FA, and where I'm signed in.
 * Reachable by every role from the sidebar account menu. */
export default function ProfilePage() {
  const { t } = useTranslation()
  const me = useMe()
  const sessions = useMySessions()
  const revoke = useRevokeMySessions()
  const [totpOpen, setTotpOpen] = useState(false)

  function handleRevoke(sessionId?: string) {
    revoke.mutate(sessionId, {
      onSuccess: (result) => toast.success(t('sessions.endedToast', { count: result.closed })),
      onError: (err) => toast.error(err instanceof ApiError ? err.message : t('sessions.endError')),
    })
  }

  if (me.isError) {
    return <ErrorState message={me.error?.message} onRetry={() => me.refetch()} />
  }

  const profile = me.data
  const otherSessions = (sessions.data ?? []).filter((s) => !s.current).length

  return (
    <div className="mx-auto flex w-full max-w-4xl flex-col gap-4">
      <Panel title={t('profile.account')}>
        {!profile ? (
          <Skeleton className="h-20 w-full" />
        ) : (
          <dl className="grid grid-cols-1 gap-x-6 gap-y-3 text-sm sm:grid-cols-2">
            <ProfileField label={t('profile.username')}>
              <span className="font-data">{profile.username}</span>
            </ProfileField>
            <ProfileField label={t('profile.fullName')}>{profile.full_name || '—'}</ProfileField>
            <ProfileField label={t('profile.role')}>
              <Badge variant="outline">{t(ROLE_LABEL_KEYS[profile.role])}</Badge>
            </ProfileField>
            <ProfileField label={t('profile.branch')}>
              {profile.branch ?? t('userManagement.allBranches')}
            </ProfileField>
            <ProfileField label={t('profile.lastLogin')}>
              {profile.last_login_at ? formatDateTime(profile.last_login_at) : '—'}
            </ProfileField>
            <ProfileField label={t('profile.passwordChanged')}>
              {profile.password_changed_at ? formatDateTime(profile.password_changed_at) : '—'}
            </ProfileField>
          </dl>
        )}
      </Panel>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
        <Panel title={t('profile.changePassword')}>
          {profile && (
            <ChangePasswordForm
              username={profile.username}
              onChanged={(closed) =>
                toast.success(t('passwordChange.successWithSessions', { count: closed }))
              }
            />
          )}
        </Panel>

        <Panel title={t('account.totpTitle')}>
          <div className="flex flex-col items-start gap-3">
            {profile?.totp_enabled ? (
              <p className="flex items-center gap-2 text-sm text-success">
                <ShieldCheck className="h-4 w-4" aria-hidden="true" />
                {t('account.totpOnDescription')}
              </p>
            ) : (
              <p className="flex items-center gap-2 text-sm text-muted-foreground">
                <ShieldOff className="h-4 w-4" aria-hidden="true" />
                {t('profile.totpOff')}
              </p>
            )}
            <Button variant="outline" size="sm" onClick={() => setTotpOpen(true)}>
              {t('profile.manageTotp')}
            </Button>
          </div>
        </Panel>
      </div>

      <Panel
        title={t('sessions.title')}
        action={
          otherSessions > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => handleRevoke()}
              disabled={revoke.isPending}
            >
              {t('sessions.endOthers')}
            </Button>
          )
        }
      >
        {sessions.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <SessionsTable
            sessions={sessions.data ?? []}
            onRevoke={handleRevoke}
            revoking={revoke.isPending}
          />
        )}
      </Panel>

      <TwoFactorDialog
        open={totpOpen}
        onOpenChange={(open) => {
          setTotpOpen(open)
          if (!open) me.refetch()
        }}
      />
    </div>
  )
}

function ProfileField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-xs text-muted-foreground">{label}</dt>
      <dd className="text-foreground">{children}</dd>
    </div>
  )
}
