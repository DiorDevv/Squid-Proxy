import { CalendarClock } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import { Input } from '@/components/ui/input'
import { formatDateTime } from '@/lib/format'
import {
  ALL_PERMISSIONS,
  PERMISSION_HINT_KEYS,
  PERMISSION_LABEL_KEYS,
  ROLE_DEFAULT_PERMISSIONS,
  isExpired,
  sortPermissions,
} from '@/lib/permissions'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { Branch } from '@/types/api'
import type { Permission, Role } from '@/types/auth'

/** Branch scope picker. `value` null = every branch. A branch-limited actor
 * (`allowUnrestricted` false) can only hand out branches it has itself --
 * `options` is already that list (GET /api/branches is scoped). */
export function BranchPicker({
  value,
  onChange,
  options,
  allowUnrestricted,
  idPrefix,
}: {
  value: string[] | null
  onChange: (value: string[] | null) => void
  options: Branch[]
  allowUnrestricted: boolean
  idPrefix: string
}) {
  const { t } = useTranslation()
  const all = value === null

  function toggle(slug: string, checked: boolean) {
    const current = new Set(value ?? [])
    if (checked) current.add(slug)
    else current.delete(slug)
    const next = options.map((o) => o.slug).filter((s) => current.has(s))
    // Unticking the last branch isn't "no access" -- keep at least one.
    if (next.length === 0) return
    onChange(next)
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3">
      {allowUnrestricted && (
        <label className="flex items-center gap-2 text-sm font-medium" htmlFor={`${idPrefix}-all`}>
          <Checkbox
            id={`${idPrefix}-all`}
            checked={all}
            onCheckedChange={(checked) =>
              onChange(checked === true ? null : options.slice(0, 1).map((o) => o.slug))
            }
          />
          {t('userManagement.allBranches')}
        </label>
      )}
      <div className={cn('flex flex-wrap gap-x-4 gap-y-2', allowUnrestricted && 'pl-6')}>
        {options.map((option) => (
          <label
            key={option.slug}
            className={cn('flex items-center gap-2 text-sm', all && 'text-muted-foreground')}
            htmlFor={`${idPrefix}-${option.slug}`}
          >
            <Checkbox
              id={`${idPrefix}-${option.slug}`}
              disabled={all}
              checked={all || (value ?? []).includes(option.slug)}
              onCheckedChange={(checked) => toggle(option.slug, checked === true)}
            />
            {option.label}
          </label>
        ))}
      </div>
      <p className="text-[11px] text-muted-foreground">{t('userManagement.branchesHint')}</p>
    </div>
  )
}

/** Feature permissions. `value` null = the role's defaults; switching to a
 * custom set starts from those defaults. `grantable` is what the actor may
 * hand out (the backend refuses anything beyond it). */
export function PermissionPicker({
  role,
  value,
  onChange,
  grantable,
  idPrefix,
}: {
  role: Role
  value: Permission[] | null
  onChange: (value: Permission[] | null) => void
  grantable: readonly Permission[]
  idPrefix: string
}) {
  const { t } = useTranslation()
  if (role === 'superadmin') {
    return (
      <p className="text-sm text-muted-foreground">
        {t('userManagement.superadminAllPermissions')}
      </p>
    )
  }
  const defaults = ROLE_DEFAULT_PERMISSIONS[role]
  const usesDefaults = value === null
  const effective = new Set(value ?? defaults)

  function toggle(permission: Permission, checked: boolean) {
    const next = new Set(effective)
    if (checked) next.add(permission)
    else next.delete(permission)
    onChange(sortPermissions(next))
  }

  return (
    <div className="flex flex-col gap-2 rounded-md border border-border p-3">
      <label
        className="flex items-center gap-2 text-sm font-medium"
        htmlFor={`${idPrefix}-defaults`}
      >
        <Checkbox
          id={`${idPrefix}-defaults`}
          checked={usesDefaults}
          onCheckedChange={(checked) => onChange(checked === true ? null : [...defaults])}
        />
        {t('userManagement.permissionsRoleDefault')}
      </label>
      <div className="grid grid-cols-1 gap-x-4 gap-y-2 pl-6 sm:grid-cols-2">
        {ALL_PERMISSIONS.map((permission) => {
          const allowed = grantable.includes(permission)
          return (
            <label
              key={permission}
              className={cn(
                'flex items-start gap-2 text-sm',
                (usesDefaults || !allowed) && 'text-muted-foreground',
              )}
              htmlFor={`${idPrefix}-${permission}`}
              title={allowed ? undefined : t('userManagement.permissionNotGrantable')}
            >
              <Checkbox
                id={`${idPrefix}-${permission}`}
                className="mt-0.5"
                disabled={usesDefaults || !allowed}
                checked={effective.has(permission)}
                onCheckedChange={(checked) => toggle(permission, checked === true)}
              />
              <span className="flex flex-col">
                <span>{t(PERMISSION_LABEL_KEYS[permission])}</span>
                <span className="text-[11px] text-muted-foreground">
                  {t(PERMISSION_HINT_KEYS[permission])}
                </span>
              </span>
            </label>
          )
        })}
      </div>
    </div>
  )
}

function toDateInput(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  const pad = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** A chosen day means "through the end of that day" in the viewer's own
 * time zone. */
function fromDateInput(value: string): string | null {
  if (!value) return null
  const [y = 0, m = 1, d = 1] = value.split('-').map(Number)
  return new Date(y, m - 1, d, 23, 59, 59).toISOString()
}

export function ExpiryField({
  value,
  onChange,
  id,
}: {
  value: string | null
  onChange: (value: string | null) => void
  id: string
}) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap items-center gap-2">
      <Input
        id={id}
        type="date"
        className="h-9 w-44"
        value={toDateInput(value)}
        onChange={(e) => onChange(fromDateInput(e.target.value))}
      />
      {value && (
        <Button type="button" variant="ghost" size="sm" onClick={() => onChange(null)}>
          {t('userManagement.expiryClear')}
        </Button>
      )}
      <p className="w-full text-[11px] text-muted-foreground">
        {value
          ? t('userManagement.expiryUntil', { date: formatDateTime(value) })
          : t('userManagement.expiryNone')}
      </p>
    </div>
  )
}

/** Compact table-cell view: branch chips, permission summary, end date. */
export function AccessSummary({
  branches,
  role,
  permissions,
  effectivePermissions,
  expiresAt,
  branchLabels,
}: {
  branches: string[] | null
  role: Role
  permissions: Permission[] | null
  effectivePermissions: Permission[]
  expiresAt: string | null
  branchLabels: Map<string, string>
}) {
  const { t } = useTranslation()
  const expired = isExpired(expiresAt)
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <div className="flex flex-wrap gap-1">
        {branches === null ? (
          <span className="text-xs text-muted-foreground">{t('userManagement.allBranches')}</span>
        ) : (
          branches.map((slug) => (
            <Badge key={slug} variant="secondary" className="text-[10px]">
              {branchLabels.get(slug) ?? slug}
            </Badge>
          ))
        )}
      </div>
      {role !== 'superadmin' && (
        <span
          className="text-[11px] text-muted-foreground"
          title={effectivePermissions.map((p) => t(PERMISSION_LABEL_KEYS[p])).join(', ')}
        >
          {permissions === null
            ? t('userManagement.permissionsSummaryDefault', { count: effectivePermissions.length })
            : t('userManagement.permissionsSummaryCustom', { count: effectivePermissions.length })}
        </span>
      )}
      {expiresAt && (
        <span
          className={cn(
            'flex items-center gap-1 text-[11px]',
            expired ? 'text-destructive' : 'text-warning',
          )}
        >
          <CalendarClock className="h-3 w-3" aria-hidden="true" />
          {expired
            ? t('userManagement.expiredOn', { date: formatDateTime(expiresAt) })
            : t('userManagement.expiresOn', { date: formatDateTime(expiresAt) })}
        </span>
      )}
    </div>
  )
}
