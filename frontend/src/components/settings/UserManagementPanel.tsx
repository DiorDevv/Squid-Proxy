import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import {
  Check,
  Copy,
  KeyRound,
  LockOpen,
  LogOut,
  MonitorSmartphone,
  MoreHorizontal,
  Pencil,
  Plus,
  Search,
  ShieldCheck,
  ShieldOff,
  TriangleAlert,
  UserRoundCheck,
  UserRoundX,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/common/ErrorState'
import { SessionsTable } from '@/components/account/SessionsTable'
import {
  useCreateUser,
  useResetUserPassword,
  useResetUserTotp,
  useRevokeUserSessions,
  useSetUserActive,
  useUnlockUser,
  useUpdateUserBranch,
  useUpdateUserProfile,
  useUpdateUserRole,
  useUserSessions,
  useUsers,
} from '@/hooks/useUsers'
import { useBranches } from '@/hooks/useBranches'
import { useAuthStore } from '@/lib/auth-store'
import { ApiError } from '@/lib/api-client'
import { formatDateTime, formatRelativeTime } from '@/lib/format'
import { USERNAME_PATTERN } from '@/lib/password-policy'
import { ROLE_LABEL_KEYS, ROLES_BY_RANK } from '@/lib/roles'
import { cn } from '@/lib/utils'
import { useTranslation } from '@/i18n'
import type { Role } from '@/types/auth'
import type { UserSummary, UserWithTemporaryPassword } from '@/types/api'

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback
}

// Radix Select requires non-empty item values, so "unrestricted" (branch =
// null) is represented by this sentinel in the UI only -- translated back
// to/from null right at the boundary, never stored or sent to the API.
const UNRESTRICTED_BRANCH_VALUE = '__all__'

type ConfirmKind = 'resetPassword' | 'deactivate' | 'resetTotp'

type DialogState =
  | { kind: 'edit'; user: UserSummary }
  | { kind: 'sessions'; user: UserSummary }
  | { kind: ConfirmKind; user: UserSummary }
  | { kind: 'temporaryPassword'; result: UserWithTemporaryPassword; reason: 'created' | 'reset' }
  | null

/** What the signed-in actor may do -- mirrors user_service on the backend
 * (which enforces it regardless): a super admin manages everyone else, an
 * admin manages only viewers (in their own scope; the list is already
 * filtered to it), nobody manages themselves here. */
function useActor() {
  const role = useAuthStore((state) => state.role)
  const username = useAuthStore((state) => state.username)
  const branch = useAuthStore((state) => state.branch)
  const isSuperadmin = role === 'superadmin'
  return {
    isSuperadmin,
    branch,
    isSelf: (user: UserSummary) => user.username === username,
    canManage: (user: UserSummary) =>
      user.username !== username && (isSuperadmin || user.role === 'viewer'),
    creatableRoles: isSuperadmin ? ROLES_BY_RANK : (['viewer'] as Role[]),
  }
}

export function UserManagementPanel() {
  const { t } = useTranslation()
  const query = useUsers()
  const [search, setSearch] = useState('')
  const [showInactive, setShowInactive] = useState(false)
  const [dialog, setDialog] = useState<DialogState>(null)

  const users = useMemo(() => query.data ?? [], [query.data])
  const inactiveCount = users.filter((u) => !u.is_active).length
  const visible = useMemo(() => {
    const needle = search.trim().toLowerCase()
    return users.filter(
      (u) =>
        (showInactive || u.is_active) &&
        (!needle ||
          [u.username, u.full_name, u.email ?? '', u.note ?? ''].some((v) =>
            v.toLowerCase().includes(needle),
          )),
    )
  }, [users, search, showInactive])

  if (query.isLoading) {
    return (
      <div className="flex flex-col gap-2">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-10 w-full" />
        ))}
      </div>
    )
  }

  if (query.isError) {
    return <ErrorState message={query.error?.message} onRetry={() => query.refetch()} />
  }

  const close = () => setDialog(null)

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <div className="relative min-w-48 flex-1 sm:max-w-xs">
          <Search
            className="pointer-events-none absolute top-1/2 left-2.5 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground"
            aria-hidden="true"
          />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={t('userManagement.searchPlaceholder')}
            aria-label={t('userManagement.searchPlaceholder')}
            className="h-8 pl-8"
          />
        </div>
        {inactiveCount > 0 && (
          <label className="flex items-center gap-2 text-xs text-muted-foreground">
            <Checkbox checked={showInactive} onCheckedChange={(v) => setShowInactive(v === true)} />
            {t('userManagement.showInactive', { count: inactiveCount })}
          </label>
        )}
        <p className="ml-auto text-xs text-muted-foreground">
          {t(
            users.length === 1
              ? 'userManagement.accountsCount_one'
              : 'userManagement.accountsCount_other',
            {
              count: users.length,
            },
          )}
        </p>
        <AddUserDialog
          onCreated={(result) =>
            setDialog({ kind: 'temporaryPassword', result, reason: 'created' })
          }
        />
      </div>

      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>{t('userManagement.columnUser')}</TableHead>
            <TableHead>{t('userManagement.columnRole')}</TableHead>
            <TableHead>{t('userManagement.columnBranch')}</TableHead>
            <TableHead>{t('userManagement.columnStatus')}</TableHead>
            <TableHead className="text-right">
              <span className="sr-only">{t('userManagement.columnActions')}</span>
            </TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {visible.length === 0 ? (
            <TableRow className="hover:bg-transparent">
              <TableCell colSpan={5} className="py-6 text-center text-sm text-muted-foreground">
                {t('userManagement.noMatches')}
              </TableCell>
            </TableRow>
          ) : (
            visible.map((user) => <UserRow key={user.id} user={user} onDialog={setDialog} />)
          )}
        </TableBody>
      </Table>

      {dialog?.kind === 'edit' && <EditUserDialog user={dialog.user} onClose={close} />}
      {dialog?.kind === 'sessions' && <UserSessionsDialog user={dialog.user} onClose={close} />}
      {(dialog?.kind === 'resetPassword' ||
        dialog?.kind === 'deactivate' ||
        dialog?.kind === 'resetTotp') && (
        <ConfirmActionDialog
          kind={dialog.kind}
          user={dialog.user}
          onClose={close}
          onPasswordReset={(result) =>
            setDialog({ kind: 'temporaryPassword', result, reason: 'reset' })
          }
        />
      )}
      {dialog?.kind === 'temporaryPassword' && (
        <TemporaryPasswordDialog result={dialog.result} reason={dialog.reason} onClose={close} />
      )}
    </div>
  )
}

function UserRow({
  user,
  onDialog,
}: {
  user: UserSummary
  onDialog: (state: DialogState) => void
}) {
  const { t } = useTranslation()
  const actor = useActor()
  const updateRole = useUpdateUserRole()
  const updateBranch = useUpdateUserBranch()
  const setActive = useSetUserActive()
  const unlock = useUnlockUser()
  const branchesQuery = useBranches()
  const branches = branchesQuery.data?.items ?? []
  const manageable = actor.canManage(user)
  const isSelf = actor.isSelf(user)
  const label = user.full_name || user.username

  function handleRoleChange(role: Role) {
    updateRole.mutate(
      { userId: user.id, role },
      {
        onSuccess: () =>
          toast.success(
            t('userManagement.toastRoleUpdated', { user: label, role: t(ROLE_LABEL_KEYS[role]) }),
          ),
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastRoleError'))),
      },
    )
  }

  function handleBranchChange(value: string) {
    const branch = value === UNRESTRICTED_BRANCH_VALUE ? null : value
    updateBranch.mutate(
      { userId: user.id, branch },
      {
        onSuccess: () => toast.success(t('userManagement.toastBranchUpdated', { user: label })),
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastBranchError'))),
      },
    )
  }

  function handleActivate() {
    setActive.mutate(
      { userId: user.id, active: true },
      {
        onSuccess: () => toast.success(t('userManagement.toastActivated', { user: label })),
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastActionError'))),
      },
    )
  }

  function handleUnlock() {
    unlock.mutate(user.id, {
      onSuccess: () => toast.success(t('userManagement.toastUnlocked', { user: label })),
      onError: (err) => toast.error(errorMessage(err, t('userManagement.toastActionError'))),
    })
  }

  return (
    <TableRow className={cn(!user.is_active && 'opacity-60')}>
      <TableCell>
        <div className="flex min-w-0 flex-col">
          <div className="flex items-center gap-2">
            <span className="truncate font-medium text-foreground">
              {user.full_name || user.username}
            </span>
            {isSelf && (
              <Badge variant="outline" className="text-[10px]">
                {t('userManagement.you')}
              </Badge>
            )}
          </div>
          <span className="truncate font-data text-xs text-muted-foreground">
            {user.username}
            {user.note && <span className="font-sans"> · {user.note}</span>}
          </span>
        </div>
      </TableCell>
      <TableCell>
        {actor.isSuperadmin && !isSelf ? (
          <Select
            value={user.role}
            onValueChange={(v) => handleRoleChange(v as Role)}
            disabled={updateRole.isPending}
          >
            <SelectTrigger
              size="sm"
              className="w-32"
              aria-label={t('userManagement.changeRoleAria', { user: user.username })}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {ROLES_BY_RANK.map((role) => (
                <SelectItem key={role} value={role}>
                  {t(ROLE_LABEL_KEYS[role])}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <Badge variant={user.role === 'superadmin' ? 'default' : 'secondary'}>
            {t(ROLE_LABEL_KEYS[user.role])}
          </Badge>
        )}
      </TableCell>
      <TableCell>
        {manageable && user.role !== 'superadmin' ? (
          <Select
            value={user.branch ?? UNRESTRICTED_BRANCH_VALUE}
            onValueChange={handleBranchChange}
            disabled={updateBranch.isPending}
          >
            <SelectTrigger
              size="sm"
              className="w-36"
              aria-label={t('userManagement.changeBranchAria', { user: user.username })}
            >
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {/* A branch-scoped actor can never grant "all branches" (the
                  API pins it to their own), so the option isn't offered. */}
              {actor.branch === null && (
                <SelectItem value={UNRESTRICTED_BRANCH_VALUE}>
                  {t('userManagement.allBranches')}
                </SelectItem>
              )}
              {branches.map((branch) => (
                <SelectItem key={branch.slug} value={branch.slug}>
                  {branch.label}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        ) : (
          <span className="text-xs text-muted-foreground">
            {user.branch ?? t('userManagement.allBranches')}
          </span>
        )}
      </TableCell>
      <TableCell>
        {/* Status and last sign-in share a column so the table fits the
            settings pane without scrolling sideways. */}
        <div className="flex flex-col gap-1">
          <StatusBadges user={user} />
          <span
            className="font-data text-[11px] text-muted-foreground"
            title={user.last_login_at ? formatDateTime(user.last_login_at) : undefined}
          >
            {t('userManagement.columnLastLogin')}:{' '}
            {user.last_login_at
              ? formatRelativeTime(user.last_login_at)
              : t('userManagement.neverSignedIn')}
            {user.last_login_ip && ` · ${user.last_login_ip}`}
          </span>
        </div>
      </TableCell>
      <TableCell className="text-right">
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon-sm"
              disabled={!manageable}
              aria-label={t('userManagement.actionsAria', { user: user.username })}
              title={manageable ? undefined : t('userManagement.notManageable')}
            >
              <MoreHorizontal className="h-4 w-4" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-52">
            <DropdownMenuItem onSelect={() => onDialog({ kind: 'edit', user })}>
              <Pencil className="h-4 w-4" aria-hidden="true" />
              {t('userManagement.actionEdit')}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => onDialog({ kind: 'sessions', user })}>
              <MonitorSmartphone className="h-4 w-4" aria-hidden="true" />
              {t('userManagement.actionSessions', { count: user.active_sessions })}
            </DropdownMenuItem>
            <DropdownMenuItem onSelect={() => onDialog({ kind: 'resetPassword', user })}>
              <KeyRound className="h-4 w-4" aria-hidden="true" />
              {t('userManagement.actionResetPassword')}
            </DropdownMenuItem>
            {user.throttled && (
              <DropdownMenuItem onSelect={handleUnlock}>
                <LockOpen className="h-4 w-4" aria-hidden="true" />
                {t('userManagement.actionUnlock')}
              </DropdownMenuItem>
            )}
            {user.totp_enabled && (
              <DropdownMenuItem onSelect={() => onDialog({ kind: 'resetTotp', user })}>
                <ShieldOff className="h-4 w-4" aria-hidden="true" />
                {t('userManagement.actionResetTotp')}
              </DropdownMenuItem>
            )}
            <DropdownMenuSeparator />
            {user.is_active ? (
              <DropdownMenuItem
                variant="destructive"
                onSelect={() => onDialog({ kind: 'deactivate', user })}
              >
                <UserRoundX className="h-4 w-4" aria-hidden="true" />
                {t('userManagement.actionDeactivate')}
              </DropdownMenuItem>
            ) : (
              <DropdownMenuItem onSelect={handleActivate}>
                <UserRoundCheck className="h-4 w-4" aria-hidden="true" />
                {t('userManagement.actionActivate')}
              </DropdownMenuItem>
            )}
          </DropdownMenuContent>
        </DropdownMenu>
      </TableCell>
    </TableRow>
  )
}

function StatusBadges({ user }: { user: UserSummary }) {
  const { t } = useTranslation()
  return (
    <div className="flex flex-wrap items-center gap-1">
      {user.is_active ? (
        <Badge variant="outline" className="border-success/40 text-[10px] text-success">
          {t('userManagement.statusActive')}
        </Badge>
      ) : (
        <Badge variant="destructive" className="text-[10px]">
          {t('userManagement.statusInactive')}
        </Badge>
      )}
      {user.must_change_password && (
        <Badge
          variant="secondary"
          className="text-[10px]"
          title={t('userManagement.statusTemporaryHint')}
        >
          {t('userManagement.statusTemporary')}
        </Badge>
      )}
      {user.throttled && (
        <Badge
          variant="destructive"
          className="text-[10px]"
          title={t('userManagement.statusLockedHint')}
        >
          {t('userManagement.statusLocked')}
        </Badge>
      )}
      {user.totp_enabled && (
        <ShieldCheck
          className="h-3.5 w-3.5 text-success"
          aria-label={t('userManagement.status2fa')}
        />
      )}
    </div>
  )
}

function AddUserDialog({ onCreated }: { onCreated: (result: UserWithTemporaryPassword) => void }) {
  const { t } = useTranslation()
  const actor = useActor()
  const [open, setOpen] = useState(false)
  const [username, setUsername] = useState('')
  const [fullName, setFullName] = useState('')
  const [note, setNote] = useState('')
  const [email, setEmail] = useState('')
  const [role, setRole] = useState<Role>('viewer')
  // A branch-scoped actor can't grant "all branches" (the API substitutes
  // their own), so default straight to their branch.
  const [branch, setBranch] = useState<string>(actor.branch ?? UNRESTRICTED_BRANCH_VALUE)
  const createUser = useCreateUser()
  const branchesQuery = useBranches()
  const branches = branchesQuery.data?.items ?? []

  const normalizedUsername = username.trim().toLowerCase()
  const usernameInvalid =
    normalizedUsername.length > 0 && !USERNAME_PATTERN.test(normalizedUsername)

  function reset() {
    setUsername('')
    setFullName('')
    setNote('')
    setEmail('')
    setRole('viewer')
    setBranch(actor.branch ?? UNRESTRICTED_BRANCH_VALUE)
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    createUser.mutate(
      {
        username: normalizedUsername,
        full_name: fullName.trim(),
        note: note.trim() || null,
        email: email.trim() || null,
        role,
        branch: role === 'superadmin' || branch === UNRESTRICTED_BRANCH_VALUE ? null : branch,
      },
      {
        onSuccess: (result) => {
          setOpen(false)
          reset()
          onCreated(result)
        },
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastCreateError'))),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button size="sm" className="gap-1.5" onClick={() => setOpen(true)}>
        <Plus className="h-3.5 w-3.5" aria-hidden="true" />
        {t('userManagement.addUser')}
      </Button>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t('userManagement.addUserTitle')}</DialogTitle>
            <DialogDescription>{t('userManagement.addUserDescription')}</DialogDescription>
          </DialogHeader>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-user-username">{t('userManagement.username')}</Label>
              <Input
                id="new-user-username"
                required
                autoCapitalize="none"
                spellCheck={false}
                autoComplete="off"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                aria-invalid={usernameInvalid}
                aria-describedby="new-user-username-hint"
                autoFocus
              />
              <p
                id="new-user-username-hint"
                className={cn(
                  'text-[11px]',
                  usernameInvalid ? 'text-destructive' : 'text-muted-foreground',
                )}
              >
                {t('userManagement.usernameHint')}
              </p>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-user-full-name">{t('userManagement.fullName')}</Label>
              <Input
                id="new-user-full-name"
                maxLength={120}
                value={fullName}
                onChange={(e) => setFullName(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-user-role">{t('userManagement.columnRole')}</Label>
              <Select
                value={role}
                onValueChange={(v) => setRole(v as Role)}
                disabled={actor.creatableRoles.length === 1}
              >
                <SelectTrigger id="new-user-role">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {actor.creatableRoles.map((r) => (
                    <SelectItem key={r} value={r}>
                      {t(ROLE_LABEL_KEYS[r])}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-user-branch">{t('userManagement.columnBranch')}</Label>
              {role === 'superadmin' ? (
                <p className="flex h-9 items-center text-sm text-muted-foreground">
                  {t('userManagement.allBranches')}
                </p>
              ) : (
                <Select value={branch} onValueChange={setBranch}>
                  <SelectTrigger id="new-user-branch">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {actor.branch === null && (
                      <SelectItem value={UNRESTRICTED_BRANCH_VALUE}>
                        {t('userManagement.allBranches')}
                      </SelectItem>
                    )}
                    {branches.map((b) => (
                      <SelectItem key={b.slug} value={b.slug}>
                        {b.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-user-email">
                {t('userManagement.email')}{' '}
                <span className="text-muted-foreground">({t('common.optional')})</span>
              </Label>
              <Input
                id="new-user-email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-1.5">
              <Label htmlFor="new-user-note">
                {t('userManagement.note')}{' '}
                <span className="text-muted-foreground">({t('common.optional')})</span>
              </Label>
              <Input
                id="new-user-note"
                maxLength={200}
                placeholder={t('userManagement.notePlaceholder')}
                value={note}
                onChange={(e) => setNote(e.target.value)}
              />
            </div>
          </div>
          <p className="rounded-md border border-border bg-muted/40 p-3 text-xs text-muted-foreground">
            {t('userManagement.temporaryPasswordExplainer')}
          </p>
          <DialogFooter>
            <Button
              type="submit"
              disabled={createUser.isPending || usernameInvalid || !normalizedUsername}
            >
              {createUser.isPending ? t('userManagement.creating') : t('userManagement.createUser')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function EditUserDialog({ user, onClose }: { user: UserSummary; onClose: () => void }) {
  const { t } = useTranslation()
  const updateProfile = useUpdateUserProfile()
  const [fullName, setFullName] = useState(user.full_name)
  const [note, setNote] = useState(user.note ?? '')
  const [email, setEmail] = useState(user.email ?? '')

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    updateProfile.mutate(
      {
        userId: user.id,
        full_name: fullName.trim(),
        note: note.trim() || null,
        email: email.trim() || null,
      },
      {
        onSuccess: () => {
          toast.success(t('userManagement.toastUpdated', { user: user.username }))
          onClose()
        },
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastActionError'))),
      },
    )
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t('userManagement.editTitle', { user: user.username })}</DialogTitle>
            <DialogDescription>{t('userManagement.editDescription')}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-user-full-name">{t('userManagement.fullName')}</Label>
            <Input
              id="edit-user-full-name"
              maxLength={120}
              value={fullName}
              onChange={(e) => setFullName(e.target.value)}
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-user-note">{t('userManagement.note')}</Label>
            <Input
              id="edit-user-note"
              maxLength={200}
              placeholder={t('userManagement.notePlaceholder')}
              value={note}
              onChange={(e) => setNote(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="edit-user-email">{t('userManagement.email')}</Label>
            <Input
              id="edit-user-email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {t('common.cancel')}
            </Button>
            <Button type="submit" disabled={updateProfile.isPending}>
              {t('common.save')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ConfirmActionDialog({
  kind,
  user,
  onClose,
  onPasswordReset,
}: {
  kind: ConfirmKind
  user: UserSummary
  onClose: () => void
  onPasswordReset: (result: UserWithTemporaryPassword) => void
}) {
  const { t } = useTranslation()
  const resetPassword = useResetUserPassword()
  const setActive = useSetUserActive()
  const resetTotp = useResetUserTotp()
  const label = user.full_name || user.username
  const pending = resetPassword.isPending || setActive.isPending || resetTotp.isPending
  const onError = (err: unknown) =>
    toast.error(errorMessage(err, t('userManagement.toastActionError')))

  const copy = {
    resetPassword: {
      title: t('userManagement.resetPasswordTitle', { user: label }),
      description: t('userManagement.resetPasswordDescription'),
      confirm: t('userManagement.actionResetPassword'),
    },
    deactivate: {
      title: t('userManagement.deactivateTitle', { user: label }),
      description: t('userManagement.deactivateDescription'),
      confirm: t('userManagement.actionDeactivate'),
    },
    resetTotp: {
      title: t('userManagement.resetTotpTitle', { user: label }),
      description: t('userManagement.resetTotpDescription'),
      confirm: t('userManagement.actionResetTotp'),
    },
  }[kind]

  function handleConfirm() {
    if (kind === 'resetPassword') {
      resetPassword.mutate(user.id, { onSuccess: onPasswordReset, onError })
    } else if (kind === 'deactivate') {
      setActive.mutate(
        { userId: user.id, active: false },
        {
          onSuccess: () => {
            toast.success(t('userManagement.toastDeactivated', { user: label }))
            onClose()
          },
          onError,
        },
      )
    } else {
      resetTotp.mutate(user.id, {
        onSuccess: () => {
          toast.success(t('userManagement.toastTotpReset', { user: label }))
          onClose()
        },
        onError,
      })
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <TriangleAlert className="h-4 w-4 text-warning" aria-hidden="true" />
            {copy.title}
          </DialogTitle>
          <DialogDescription>{copy.description}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            {t('common.cancel')}
          </Button>
          <Button
            variant={kind === 'deactivate' ? 'destructive' : 'default'}
            onClick={handleConfirm}
            disabled={pending}
          >
            {copy.confirm}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

/** The one and only time a temporary password is visible -- the backend
 * never returns it again. */
function TemporaryPasswordDialog({
  result,
  reason,
  onClose,
}: {
  result: UserWithTemporaryPassword
  reason: 'created' | 'reset'
  onClose: () => void
}) {
  const { t } = useTranslation()
  const [copied, setCopied] = useState(false)

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(result.temporary_password)
      setCopied(true)
    } catch {
      toast.error(t('userManagement.copyFailed'))
    }
  }

  return (
    // Not dismissable by clicking outside -- losing this dialog by accident
    // means resetting the password again.
    <Dialog open onOpenChange={() => {}}>
      <DialogContent showCloseButton={false} onInteractOutside={(e) => e.preventDefault()}>
        <DialogHeader>
          <DialogTitle>
            {reason === 'created'
              ? t('userManagement.tempCreatedTitle', { user: result.user.username })
              : t('userManagement.tempResetTitle', { user: result.user.username })}
          </DialogTitle>
          <DialogDescription>{t('userManagement.tempDescription')}</DialogDescription>
        </DialogHeader>
        <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 rounded-md border border-border bg-muted/40 p-3">
          <dt className="text-xs text-muted-foreground">{t('userManagement.username')}</dt>
          <dd className="font-data text-sm text-foreground">{result.user.username}</dd>
          <dt className="text-xs text-muted-foreground">{t('userManagement.temporaryPassword')}</dt>
          <dd className="flex items-center gap-2">
            <code className="font-data text-base font-semibold tracking-wide whitespace-nowrap text-foreground select-all">
              {result.temporary_password}
            </code>
            <Button
              variant="outline"
              size="icon-sm"
              onClick={handleCopy}
              aria-label={t('userManagement.copy')}
            >
              {copied ? (
                <Check className="h-3.5 w-3.5 text-success" />
              ) : (
                <Copy className="h-3.5 w-3.5" />
              )}
            </Button>
          </dd>
        </dl>
        <p className="flex items-start gap-2 text-xs text-warning">
          <TriangleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" aria-hidden="true" />
          {t('userManagement.tempWarning')}
        </p>
        <DialogFooter>
          <Button onClick={onClose}>{t('userManagement.tempDone')}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function UserSessionsDialog({ user, onClose }: { user: UserSummary; onClose: () => void }) {
  const { t } = useTranslation()
  const sessions = useUserSessions(user.id)
  const revoke = useRevokeUserSessions()

  function handleRevoke(sessionId?: string) {
    revoke.mutate(
      { userId: user.id, sessionId },
      {
        onSuccess: (result) => {
          toast.success(t('sessions.endedToast', { count: result.closed }))
          sessions.refetch()
        },
        onError: (err) => toast.error(errorMessage(err, t('sessions.endError'))),
      },
    )
  }

  const count = sessions.data?.length ?? 0

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {t('userManagement.sessionsTitle', { user: user.full_name || user.username })}
          </DialogTitle>
          <DialogDescription>{t('userManagement.sessionsDescription')}</DialogDescription>
        </DialogHeader>
        {sessions.isLoading ? (
          <Skeleton className="h-24 w-full" />
        ) : (
          <SessionsTable
            sessions={sessions.data ?? []}
            onRevoke={handleRevoke}
            revoking={revoke.isPending}
          />
        )}
        <DialogFooter>
          {count > 0 && (
            <Button
              variant="destructive"
              onClick={() => handleRevoke()}
              disabled={revoke.isPending}
              className="gap-1.5"
            >
              <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
              {t('userManagement.endAllSessions')}
            </Button>
          )}
          <Button variant="outline" onClick={onClose}>
            {t('common.close')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
