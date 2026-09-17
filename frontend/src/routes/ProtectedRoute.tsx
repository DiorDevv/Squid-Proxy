import { Loader2 } from 'lucide-react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/lib/auth-store'
import { useTranslation } from '@/i18n'
import type { Role } from '@/types/auth'

interface ProtectedRouteProps {
  /** One role, or any-of a list. Omitted = any authenticated user. */
  requiredRole?: Role | Role[]
}

export function ProtectedRoute({ requiredRole }: ProtectedRouteProps) {
  const { t } = useTranslation()
  const status = useAuthStore((state) => state.status)
  const role = useAuthStore((state) => state.role)

  if (status === 'checking') {
    return (
      <div className="flex h-svh animate-in fade-in items-center justify-center gap-2 bg-background text-muted-foreground duration-300">
        <Loader2 className="h-4 w-4 animate-spin text-primary" aria-hidden="true" />
        <span className="font-data text-sm">{t('session.verifying')}</span>
      </div>
    )
  }

  if (status === 'unauthenticated') {
    return <Navigate to="/login" replace />
  }

  if (requiredRole) {
    const allowed = Array.isArray(requiredRole) ? requiredRole : [requiredRole]
    if (!role || !allowed.includes(role)) {
      return <Navigate to="/" replace />
    }
  }

  return <Outlet />
}
