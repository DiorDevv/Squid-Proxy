import { useEffect, useRef } from 'react'
import { Route, Routes } from 'react-router-dom'
import { AppShell } from '@/components/layout/AppShell'
import { ProtectedRoute } from '@/routes/ProtectedRoute'
import { useAuth } from '@/hooks/useAuth'
import LoginPage from '@/pages/LoginPage'
import DashboardPage from '@/pages/DashboardPage'
import ClientsPage from '@/pages/ClientsPage'
import ClientDetailPage from '@/pages/ClientDetailPage'
import BlockedPage from '@/pages/BlockedPage'
import DomainsPage from '@/pages/DomainsPage'
import DomainDetailPage from '@/pages/DomainDetailPage'
import SettingsPage from '@/pages/SettingsPage'
import NotFoundPage from '@/pages/NotFoundPage'

export default function App() {
  const { bootstrap } = useAuth()
  const bootstrapped = useRef(false)

  useEffect(() => {
    if (bootstrapped.current) return
    bootstrapped.current = true
    bootstrap()
  }, [bootstrap])

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route element={<ProtectedRoute />}>
        <Route element={<AppShell />}>
          <Route index element={<DashboardPage />} />
          <Route path="clients" element={<ClientsPage />} />
          <Route path="clients/:clientIp" element={<ClientDetailPage />} />
          <Route path="blocked" element={<BlockedPage />} />
          <Route path="domains" element={<DomainsPage />} />
          <Route path="domains/:domain" element={<DomainDetailPage />} />
          <Route element={<ProtectedRoute requiredRole="admin" />}>
            <Route path="settings" element={<SettingsPage />} />
          </Route>
        </Route>
      </Route>

      <Route path="*" element={<NotFoundPage />} />
    </Routes>
  )
}
