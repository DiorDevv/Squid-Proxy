import { lazy, Suspense, useEffect, useRef } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { Skeleton } from '@/components/ui/skeleton'
import { useAuth } from '@/hooks/useAuth'

// Route-level code-splitting: with no dynamic imports anywhere, the whole
// app (React, every Radix primitive, Recharts, react-table, every page)
// shipped as one >1MB JS chunk regardless of which page was actually
// requested. Each of these becomes its own chunk, loaded only once its
// route is actually visited.
const LoginPage = lazy(() => import('@/pages/LoginPage'))
const DashboardPage = lazy(() => import('@/pages/DashboardPage'))
const ClientsPage = lazy(() => import('@/pages/ClientsPage'))
const ClientDetailPage = lazy(() => import('@/pages/ClientDetailPage'))
const BlockedPage = lazy(() => import('@/pages/BlockedPage'))
const EventsPage = lazy(() => import('@/pages/EventsPage'))
const DomainsPage = lazy(() => import('@/pages/DomainsPage'))
const DomainDetailPage = lazy(() => import('@/pages/DomainDetailPage'))
const SettingsPage = lazy(() => import('@/pages/SettingsPage'))
const NotFoundPage = lazy(() => import('@/pages/NotFoundPage'))

function RouteFallback() {
  return (
    <div className="flex flex-col gap-3 p-6">
      <Skeleton className="h-8 w-48" />
      <Skeleton className="h-32 w-full" />
      <Skeleton className="h-32 w-full" />
    </div>
  )
}

export default function App() {
  const { bootstrap } = useAuth()
  const bootstrapped = useRef(false)

  useEffect(() => {
    if (bootstrapped.current) return
    bootstrapped.current = true
    bootstrap()
  }, [bootstrap])

  return (
    <Suspense fallback={<RouteFallback />}>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<ProtectedRoute />}>
          <Route element={<AppShell />}>
            <Route index element={<DashboardPage />} />
            <Route path="clients" element={<ClientsPage />} />
            <Route path="clients/:clientIp" element={<ClientDetailPage />} />
            <Route path="blocked" element={<BlockedPage />} />
            <Route path="events" element={<EventsPage />} />
            <Route path="domains" element={<DomainsPage />} />
            <Route path="domains/:domain" element={<DomainDetailPage />} />
            <Route element={<ProtectedRoute requiredRole="admin" />}>
              <Route path="settings" element={<SettingsPage />} />
            </Route>
          </Route>
        </Route>

        <Route path="*" element={<NotFoundPage />} />
      </Routes>
    </Suspense>
  )
}
