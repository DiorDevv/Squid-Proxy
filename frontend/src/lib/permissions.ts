import type { TranslationKey } from '@/i18n'
import type { Permission, Role } from '@/types/auth'

/** Feature permissions in display order -- mirrors backend
 * core/permissions.py (which is what actually enforces them). */
export const ALL_PERMISSIONS: readonly Permission[] = [
  'export',
  'raw_export',
  'watchlist',
  'reports',
  'subject_access',
  'categories',
  'alerts',
  'audit',
]

/** What each role gets when an account carries no explicit list. */
export const ROLE_DEFAULT_PERMISSIONS: Record<Role, readonly Permission[]> = {
  superadmin: ALL_PERMISSIONS,
  admin: ALL_PERMISSIONS,
  auditor: ['export', 'audit'],
  viewer: [],
}

export const PERMISSION_LABEL_KEYS: Record<Permission, TranslationKey> = {
  export: 'permissions.export',
  raw_export: 'permissions.raw_export',
  watchlist: 'permissions.watchlist',
  reports: 'permissions.reports',
  subject_access: 'permissions.subject_access',
  categories: 'permissions.categories',
  alerts: 'permissions.alerts',
  audit: 'permissions.audit',
}

export const PERMISSION_HINT_KEYS: Record<Permission, TranslationKey> = {
  export: 'permissions.exportHint',
  raw_export: 'permissions.raw_exportHint',
  watchlist: 'permissions.watchlistHint',
  reports: 'permissions.reportsHint',
  subject_access: 'permissions.subject_accessHint',
  categories: 'permissions.categoriesHint',
  alerts: 'permissions.alertsHint',
  audit: 'permissions.auditHint',
}

/** Permissions that open a page under Settings -- anyone holding one of
 * these (or an admin) gets the Settings menu entry. */
export const SETTINGS_PERMISSIONS: readonly Permission[] = [
  'raw_export',
  'watchlist',
  'reports',
  'categories',
  'alerts',
  'audit',
]

export function sortPermissions(permissions: Iterable<Permission>): Permission[] {
  const set = new Set(permissions)
  return ALL_PERMISSIONS.filter((p) => set.has(p))
}

/** Has this account's access end date passed? null = no end date. */
export function isExpired(expiresAt: string | null): boolean {
  return expiresAt !== null && new Date(expiresAt).getTime() <= Date.now()
}
