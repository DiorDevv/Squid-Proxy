import { lazy } from 'react'
import { Loader2 } from 'lucide-react'
import { Navigate, Outlet } from 'react-router-dom'
import { useAuthStore } from '@/lib/auth-store'
import { useTranslation } from '@/i18n'
import type { Permission, Role } from '@/types/auth'

const ForcePasswordChangePage = lazy(() => import('@/pages/ForcePasswordChangePage'))

interface ProtectedRouteProps {
  /** One role, or any-of a list. Omitted = any authenticated user. A super
   * admin passes wherever 'admin' is allowed (same as the backend). */
  requiredRole?: Role | Role[]
  /** Any-of. Combined with requiredRole, either one is enough. */
  requiredPermission?: Permission | Permission[]
}

export function ProtectedRoute({ requiredRole, requiredPermission }: ProtectedRouteProps) {
  const { t } = useTranslation()
  const status = useAuthStore((state) => state.status)
  const role = useAuthStore((state) => state.role)
  const permissions = useAuthStore((state) => state.permissions)
  const mustChangePassword = useAuthStore((state) => state.mustChangePassword)

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

  // Signed in on an admin-issued temporary password: nothing else is
  // reachable until it's changed (the API refuses everything else too).
  if (mustChangePassword) {
    return <ForcePasswordChangePage />
  }

  if (requiredRole || requiredPermission) {
    const allowedRoles = requiredRole ? (Array.isArray(requiredRole) ? requiredRole : [requiredRole]) : []
    const effective = allowedRoles.includes('admin') ? [...allowedRoles, 'superadmin'] : allowedRoles
    const roleOk = role !== null && effective.includes(role)
    const wanted = requiredPermission
      ? Array.isArray(requiredPermission)
        ? requiredPermission
        : [requiredPermission]
      : []
    const permissionOk = wanted.some((p) => permissions.includes(p))
    if (!roleOk && !permissionOk) {
      return <Navigate to="/" replace />
    }
  }

  return <Outlet />
}
