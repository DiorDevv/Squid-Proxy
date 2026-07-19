import { useState } from 'react'
import { Menu, Radar } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { NavLinks } from '@/components/layout/NavLinks'
import { SidebarUserMenu } from '@/components/layout/SidebarUserMenu'
import { useTranslation } from '@/i18n'

export function MobileNav() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)

  return (
    <Sheet open={open} onOpenChange={setOpen}>
      <SheetTrigger asChild>
        <Button variant="ghost" size="icon-sm" className="md:hidden" aria-label={t('topbar.openMenu')}>
          <Menu className="h-5 w-5" />
        </Button>
      </SheetTrigger>
      <SheetContent side="left" className="flex w-64 flex-col bg-sidebar p-0">
        <SheetHeader className="flex-row items-center gap-2.5 space-y-0 px-4 py-4">
          <div className="gradient-warning flex h-8 w-8 items-center justify-center rounded-lg shadow-[0_0_16px_-4px_var(--warning)]">
            <Radar className="h-4 w-4 text-white" aria-hidden="true" />
          </div>
          <SheetTitle className="text-gradient-brand text-sm font-bold tracking-wide">
            SQUID WATCH
          </SheetTitle>
        </SheetHeader>
        <nav className="flex flex-col gap-1 px-2" aria-label={t('nav.primaryLandmark')}>
          <NavLinks onNavigate={() => setOpen(false)} />
        </nav>
        <SidebarUserMenu />
      </SheetContent>
    </Sheet>
  )
}
