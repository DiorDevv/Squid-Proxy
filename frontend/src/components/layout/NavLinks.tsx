import { NavLink } from 'react-router-dom'
import { Globe, LayoutDashboard, ShieldAlert, Settings, Users } from 'lucide-react'
import { cn } from '@/lib/utils'
import { useAuthStore } from '@/lib/auth-store'
import { useLiveEvents } from '@/hooks/useLiveEvents'
import { useTranslation, type TranslationKey } from '@/i18n'

export const NAV_ITEMS: { to: string; labelKey: TranslationKey; icon: typeof LayoutDashboard; end: boolean }[] = [
  { to: '/', labelKey: 'nav.dashboard', icon: LayoutDashboard, end: true },
  { to: '/clients', labelKey: 'nav.clients', icon: Users, end: false },
  { to: '/blocked', labelKey: 'nav.blocked', icon: ShieldAlert, end: false },
  { to: '/domains', labelKey: 'nav.domains', icon: Globe, end: false },
]

interface NavLinksProps {
  onNavigate?: () => void
}

export function NavLinks({ onNavigate }: NavLinksProps) {
  const { t } = useTranslation()
  const role = useAuthStore((state) => state.role)
  const { events } = useLiveEvents()
  const blockedCount = events.reduce((count, event) => count + (event.blocked ? 1 : 0), 0)

  const linkClassName = ({ isActive }: { isActive: boolean }) =>
    cn(
      'group relative flex items-center gap-2.5 rounded-md border-l-2 border-transparent px-3 py-2 text-sm font-medium transition-all duration-150',
      'text-sidebar-foreground hover:translate-x-0.5 hover:bg-secondary hover:text-foreground',
      isActive &&
        'border-l-primary bg-gradient-to-r from-primary/15 to-transparent text-primary hover:translate-x-0 hover:text-primary',
    )

  const iconClassName = (isActive: boolean) =>
    cn(
      'h-4 w-4 transition-colors',
      isActive ? 'text-primary' : 'text-muted-foreground group-hover:text-foreground',
    )

  return (
    <>
      {NAV_ITEMS.map(({ to, labelKey, icon: Icon, end }) => (
        <NavLink key={to} to={to} end={end} className={linkClassName} onClick={onNavigate}>
          {({ isActive }) => (
            <>
              <Icon className={iconClassName(isActive)} aria-hidden="true" />
              <span className="flex-1">{t(labelKey)}</span>
              {to === '/blocked' && blockedCount > 0 && (
                <span
                  className="font-data flex h-4.5 min-w-4.5 shrink-0 items-center justify-center rounded-full bg-warning/15 px-1 text-[10px] font-semibold text-warning"
                  aria-label={t('nav.blockedCount', { count: blockedCount })}
                >
                  {blockedCount > 99 ? '99+' : blockedCount}
                </span>
              )}
            </>
          )}
        </NavLink>
      ))}
      {role === 'admin' && (
        <NavLink to="/settings" className={linkClassName} onClick={onNavigate}>
          {({ isActive }) => (
            <>
              <Settings className={iconClassName(isActive)} aria-hidden="true" />
              <span className="flex-1">{t('nav.settings')}</span>
            </>
          )}
        </NavLink>
      )}
    </>
  )
}
