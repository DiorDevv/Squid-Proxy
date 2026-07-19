import { Radar } from 'lucide-react'
import { NavLinks } from '@/components/layout/NavLinks'
import { SidebarUserMenu } from '@/components/layout/SidebarUserMenu'
import { useTranslation } from '@/i18n'

export function Sidebar() {
  const { t } = useTranslation()
  return (
    <aside className="hidden w-56 shrink-0 flex-col border-r border-sidebar-border bg-sidebar md:flex">
      <div className="flex items-center gap-2.5 px-4 py-4">
        <div className="gradient-warning flex h-8 w-8 items-center justify-center rounded-lg shadow-[0_0_16px_-4px_var(--warning)]">
          <Radar className="h-4 w-4 text-white" aria-hidden="true" />
        </div>
        <span className="text-gradient-brand text-sm font-bold tracking-wide">SQUID WATCH</span>
      </div>
      <nav className="flex flex-1 flex-col gap-1 px-2 py-2" aria-label={t('nav.primaryLandmark')}>
        <NavLinks />
      </nav>
      <SidebarUserMenu />
    </aside>
  )
}
