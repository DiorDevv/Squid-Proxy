import { useState } from 'react'
import { KeyRound, LogOut, MoreVertical } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import { ThemeSwitcher } from '@/components/layout/ThemeSwitcher'
import { LanguageSwitcher } from '@/components/layout/LanguageSwitcher'
import { TwoFactorDialog } from '@/components/account/TwoFactorDialog'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/lib/auth-store'
import { useTranslation } from '@/i18n'

/** Persistent account footer shown at the bottom of the sidebar (desktop)
 * and the mobile nav sheet, so "who am I / sign out" is always one click
 * away instead of hiding behind a topbar icon -- the same pattern used by
 * Linear/Vercel/Grafana-style dashboards. Also hosts the color-theme and
 * language pickers, since those are per-user preferences too and (unlike
 * the admin-only Settings page) need to stay reachable by every role. */
export function SidebarUserMenu() {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const navigate = useNavigate()
  const email = useAuthStore((state) => state.email)
  const role = useAuthStore((state) => state.role)
  const [totpDialogOpen, setTotpDialogOpen] = useState(false)

  const label = email ?? (role ? `${role} account` : t('account.signedIn'))
  const initials = (email ?? role ?? '?').charAt(0).toUpperCase()

  async function handleLogout() {
    await logout()
    toast.success(t('account.signedOutToast'))
    navigate('/login', { replace: true })
  }

  return (
    <div className="mt-auto border-t border-sidebar-border p-2">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <button
            type="button"
            className="group flex w-full items-center gap-2.5 rounded-md px-2 py-2 text-left transition-colors hover:bg-secondary"
          >
            <span className="gradient-info flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-semibold text-white">
              {initials}
            </span>
            <span className="flex min-w-0 flex-1 flex-col">
              <span className="truncate text-xs font-medium text-sidebar-foreground">{label}</span>
              <span className="text-[10px] font-medium tracking-wide text-muted-foreground uppercase">
                {role}
              </span>
            </span>
            <MoreVertical
              className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground"
              aria-hidden="true"
            />
          </button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" side="top" className="w-56">
          <DropdownMenuLabel>
            <div className="flex flex-col">
              <span className="text-sm">{email ?? t('account.signedIn')}</span>
              <span className="text-xs font-normal text-muted-foreground capitalize">{role}</span>
            </div>
          </DropdownMenuLabel>
          <DropdownMenuSeparator />
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-xs text-muted-foreground">{t('account.theme')}</span>
            <ThemeSwitcher />
          </div>
          <div className="flex items-center justify-between px-2 py-1.5">
            <span className="text-xs text-muted-foreground">{t('account.language')}</span>
            <LanguageSwitcher />
          </div>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            onSelect={(e) => {
              // Keep the dropdown's own closing from also stealing focus
              // away from the dialog that's about to open (a known Radix
              // gotcha when a Dialog is triggered from inside a
              // DropdownMenu item rather than a plain DialogTrigger).
              e.preventDefault()
              setTotpDialogOpen(true)
            }}
          >
            <KeyRound className="h-4 w-4" aria-hidden="true" />
            {t('account.totpMenuItem')}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={handleLogout} variant="destructive">
            <LogOut className="h-4 w-4" aria-hidden="true" />
            {t('account.signOut')}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <TwoFactorDialog open={totpDialogOpen} onOpenChange={setTotpDialogOpen} />
    </div>
  )
}
