import { Outlet, useLocation } from 'react-router-dom'
import { Sidebar } from '@/components/layout/Sidebar'
import { Topbar } from '@/components/layout/Topbar'
import { LogHealthBanner } from '@/components/layout/LogHealthBanner'
import { LiveEventsContext, useLiveEventsSource } from '@/hooks/useLiveEvents'

export function AppShell() {
  const liveEvents = useLiveEventsSource(50)
  const location = useLocation()

  return (
    <LiveEventsContext.Provider value={liveEvents}>
      <div className="flex h-svh w-full overflow-hidden bg-background">
        <Sidebar />
        <div className="flex min-w-0 flex-1 flex-col">
          <Topbar />
          <LogHealthBanner />
          <main className="flex-1 overflow-y-auto p-4 md:p-6">
            {/* Keyed by path so each navigation re-triggers the entrance
                animation instead of reusing the previous page's DOM node. */}
            <div key={location.pathname} className="animate-in fade-in slide-in-from-bottom-1 duration-200">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </LiveEventsContext.Provider>
  )
}
