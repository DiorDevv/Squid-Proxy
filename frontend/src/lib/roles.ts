import type { TranslationKey } from '@/i18n'
import type { Role } from '@/types/auth'

export const ROLE_LABEL_KEYS: Record<Role, TranslationKey> = {
  superadmin: 'userManagement.roleSuperadmin',
  admin: 'userManagement.roleAdmin',
  viewer: 'userManagement.roleViewer',
  auditor: 'userManagement.roleAuditor',
}

/** Most to least privileged -- the order role pickers list them in. */
export const ROLES_BY_RANK: Role[] = ['superadmin', 'admin', 'auditor', 'viewer']
