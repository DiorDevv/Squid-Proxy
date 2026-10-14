import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from '@/hooks/useAuth'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import { visibleSettingsItems } from '@/pages/settings/settings-nav'

/** Splits what used to be one long, nine-panel scroll into focused
 * sub-pages (own URL each, e.g. /settings/export) behind this shared side
 * nav. Which ones show depends on role and permissions -- see
 * settings-nav.ts. */
export default function SettingsLayout() {
  const { t } = useTranslation()
  const { branch, role, permissions } = useAuth()
  const navItems = visibleSettingsItems(role, permissions, branch === null)
  return (
    <div className="flex flex-col gap-4 sm:flex-row sm:gap-6">
      <nav className="flex shrink-0 flex-row gap-1 overflow-x-auto sm:w-48 sm:flex-col sm:overflow-visible">
        {navItems.map(({ to, labelKey }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'shrink-0 rounded-md border-l-2 border-transparent px-3 py-2 text-sm font-medium whitespace-nowrap transition-all duration-150',
                'text-muted-foreground hover:bg-secondary hover:text-foreground',
                isActive &&
                  'border-l-primary bg-gradient-to-r from-primary/15 to-transparent text-primary hover:text-primary',
              )
            }
          >
            {t(labelKey)}
          </NavLink>
        ))}
      </nav>
      <div className="min-w-0 flex-1">
        <Outlet />
      </div>
    </div>
  )
}
