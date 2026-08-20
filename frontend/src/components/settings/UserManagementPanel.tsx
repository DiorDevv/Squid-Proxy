import { useState } from 'react'
import { toast } from 'sonner'
import { KeyRound, Plus, Trash2, UserRound } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { ErrorState } from '@/components/common/ErrorState'
import {
  useCreateUser,
  useDeleteUser,
  useResetUserPassword,
  useUpdateUserBranch,
  useUpdateUserRole,
  useUsers,
} from '@/hooks/useUsers'
import { useBranches } from '@/hooks/useBranches'
import { useAuthStore } from '@/lib/auth-store'
import { ApiError } from '@/lib/api-client'
import { formatDateTime } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { Role } from '@/types/auth'
import type { UserSummary } from '@/types/api'

function errorMessage(err: unknown, fallback: string): string {
  return err instanceof ApiError ? err.message : fallback
}

export function UserManagementPanel() {
  const { t } = useTranslation()
  const query = useUsers()
  const currentEmail = useAuthStore((state) => state.email)

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

  const users = query.data ?? []

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <p className="text-xs text-muted-foreground">
          {t(users.length === 1 ? 'userManagement.accountsCount_one' : 'userManagement.accountsCount_other', {
            count: users.length,
          })}
        </p>
        <AddUserDialog />
      </div>

      <Table>
        <TableHeader>
          <TableRow className="hover:bg-transparent">
            <TableHead>{t('userManagement.columnEmail')}</TableHead>
            <TableHead>{t('userManagement.columnRole')}</TableHead>
            <TableHead>{t('userManagement.columnBranch')}</TableHead>
            <TableHead>{t('userManagement.columnCreated')}</TableHead>
            <TableHead className="text-right">{t('userManagement.columnActions')}</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {users.map((user) => (
            <UserRow key={user.id} user={user} isSelf={user.email === currentEmail} />
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

// Radix Select requires non-empty item values, so "unrestricted" (branch =
// null) is represented by this sentinel in the UI only -- translated back
// to/from null right at the boundary (handleBranchChange / the initial
// Select value below), never stored or sent to the API as this string.
const UNRESTRICTED_BRANCH_VALUE = '__all__'

function UserRow({ user, isSelf }: { user: UserSummary; isSelf: boolean }) {
  const { t } = useTranslation()
  const updateRole = useUpdateUserRole()
  const updateBranch = useUpdateUserBranch()
  const branchesQuery = useBranches()
  const branches = branchesQuery.data?.items ?? []
  // A branch-scoped viewer can never actually grant "all branches" -- the
  // API silently substitutes their own branch instead of erroring (see
  // user_service._enforce_actor_branch), so offering the option here would
  // just be a control that quietly does something other than what it says.
  const viewerBranch = useAuthStore((state) => state.branch)

  function handleRoleChange(role: Role) {
    updateRole.mutate(
      { userId: user.id, role },
      {
        onSuccess: () => toast.success(t('userManagement.toastRoleUpdated', { email: user.email, role })),
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastRoleError'))),
      },
    )
  }

  function handleBranchChange(value: string) {
    const branch = value === UNRESTRICTED_BRANCH_VALUE ? null : value
    updateBranch.mutate(
      { userId: user.id, branch },
      {
        onSuccess: () => toast.success(t('userManagement.toastBranchUpdated', { email: user.email })),
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastBranchError'))),
      },
    )
  }

  return (
    <TableRow>
      <TableCell>
        <div className="flex items-center gap-2">
          <span className="font-data text-foreground">{user.email}</span>
          {isSelf && (
            <Badge variant="outline" className="text-[10px]">
              {t('userManagement.you')}
            </Badge>
          )}
        </div>
      </TableCell>
      <TableCell>
        <Select value={user.role} onValueChange={handleRoleChange} disabled={isSelf || updateRole.isPending}>
          <SelectTrigger
            size="sm"
            className="w-28"
            aria-label={t('userManagement.changeRoleAria', { email: user.email })}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="admin">{t('userManagement.roleAdmin')}</SelectItem>
            <SelectItem value="viewer">{t('userManagement.roleViewer')}</SelectItem>
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        <Select
          value={user.branch ?? UNRESTRICTED_BRANCH_VALUE}
          onValueChange={handleBranchChange}
          disabled={updateBranch.isPending}
        >
          <SelectTrigger
            size="sm"
            className="w-36"
            aria-label={t('userManagement.changeBranchAria', { email: user.email })}
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {viewerBranch === null && (
              <SelectItem value={UNRESTRICTED_BRANCH_VALUE}>{t('userManagement.allBranches')}</SelectItem>
            )}
            {branches.map((branch) => (
              <SelectItem key={branch.slug} value={branch.slug}>
                {branch.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </TableCell>
      <TableCell>
        <span className="font-data text-xs text-muted-foreground">{formatDateTime(user.created_at)}</span>
      </TableCell>
      <TableCell className="text-right">
        <div className="flex justify-end gap-1.5">
          <ResetPasswordDialog user={user} />
          <DeleteUserDialog user={user} disabled={isSelf} />
        </div>
      </TableCell>
    </TableRow>
  )
}

function AddUserDialog() {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [role, setRole] = useState<Role>('viewer')
  // A branch-scoped viewer can never actually grant "all branches" -- the
  // API silently substitutes their own branch instead of erroring (see
  // user_service._enforce_actor_branch), so default straight to it instead
  // of a picker option that would quietly do something other than what it
  // says once submitted.
  const viewerBranch = useAuthStore((state) => state.branch)
  const [branch, setBranch] = useState<string>(viewerBranch ?? UNRESTRICTED_BRANCH_VALUE)
  const createUser = useCreateUser()
  const branchesQuery = useBranches()
  const branches = branchesQuery.data?.items ?? []

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    createUser.mutate(
      { email, password, role, branch: branch === UNRESTRICTED_BRANCH_VALUE ? null : branch },
      {
        onSuccess: () => {
          toast.success(t('userManagement.toastUserCreated', { email, role }))
          setOpen(false)
          setEmail('')
          setPassword('')
          setRole('viewer')
          setBranch(viewerBranch ?? UNRESTRICTED_BRANCH_VALUE)
        },
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastCreateError'))),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button size="sm" className="gap-1.5">
          <Plus className="h-3.5 w-3.5" aria-hidden="true" />
          {t('userManagement.addUser')}
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t('userManagement.addUserTitle')}</DialogTitle>
            <DialogDescription>{t('userManagement.addUserDescription')}</DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-user-email">{t('userManagement.columnEmail')}</Label>
            <Input
              id="new-user-email"
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoFocus
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-user-password">{t('userManagement.newPassword')}</Label>
            <Input
              id="new-user-password"
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-user-role">{t('userManagement.columnRole')}</Label>
            <Select value={role} onValueChange={(v) => setRole(v as Role)}>
              <SelectTrigger id="new-user-role">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="admin">{t('userManagement.roleAdmin')}</SelectItem>
                <SelectItem value="viewer">{t('userManagement.roleViewer')}</SelectItem>
              </SelectContent>
            </Select>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="new-user-branch">{t('userManagement.columnBranch')}</Label>
            <Select value={branch} onValueChange={setBranch}>
              <SelectTrigger id="new-user-branch">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {viewerBranch === null && (
                  <SelectItem value={UNRESTRICTED_BRANCH_VALUE}>{t('userManagement.allBranches')}</SelectItem>
                )}
                {branches.map((b) => (
                  <SelectItem key={b.slug} value={b.slug}>
                    {b.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          <DialogFooter>
            <Button type="submit" disabled={createUser.isPending}>
              {createUser.isPending ? t('userManagement.creating') : t('userManagement.createUser')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function ResetPasswordDialog({ user }: { user: UserSummary }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const [newPassword, setNewPassword] = useState('')
  const resetPassword = useResetUserPassword()

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    resetPassword.mutate(
      { userId: user.id, newPassword },
      {
        onSuccess: () => {
          toast.success(t('userManagement.toastPasswordReset', { email: user.email }))
          setOpen(false)
          setNewPassword('')
        },
        onError: (err) => toast.error(errorMessage(err, t('userManagement.toastPasswordError'))),
      },
    )
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="icon-sm"
          aria-label={t('userManagement.resetPasswordAria', { email: user.email })}
        >
          <KeyRound className="h-3.5 w-3.5" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <DialogHeader>
            <DialogTitle>{t('userManagement.resetPasswordTitle')}</DialogTitle>
            <DialogDescription>
              {t('userManagement.resetPasswordDescription', { email: user.email })}
            </DialogDescription>
          </DialogHeader>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="reset-password-input">{t('userManagement.newPasswordLabel')}</Label>
            <Input
              id="reset-password-input"
              type="password"
              required
              minLength={8}
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              autoFocus
            />
          </div>
          <DialogFooter>
            <Button type="submit" disabled={resetPassword.isPending}>
              {resetPassword.isPending ? t('userManagement.resetting') : t('userManagement.resetPassword')}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function DeleteUserDialog({ user, disabled }: { user: UserSummary; disabled: boolean }) {
  const { t } = useTranslation()
  const [open, setOpen] = useState(false)
  const deleteUser = useDeleteUser()

  function handleDelete() {
    deleteUser.mutate(user.id, {
      onSuccess: () => {
        toast.success(t('userManagement.toastUserDeleted', { email: user.email }))
        setOpen(false)
      },
      onError: (err) => toast.error(errorMessage(err, t('userManagement.toastDeleteError'))),
    })
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button
          variant="outline"
          size="icon-sm"
          disabled={disabled}
          aria-label={t('userManagement.deleteAria', { email: user.email })}
          title={disabled ? t('userManagement.deleteDisabledTitle') : undefined}
        >
          <Trash2 className="h-3.5 w-3.5 text-destructive" />
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <UserRound className="h-4 w-4 text-destructive" aria-hidden="true" />
            {t('userManagement.deleteTitle', { email: user.email })}
          </DialogTitle>
          <DialogDescription>{t('userManagement.deleteDescription')}</DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="destructive" onClick={handleDelete} disabled={deleteUser.isPending}>
            {deleteUser.isPending ? t('userManagement.deleting') : t('userManagement.deleteAccount')}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
