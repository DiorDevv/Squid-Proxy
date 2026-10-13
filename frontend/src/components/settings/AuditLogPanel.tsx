import { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { DataTable } from '@/components/common/DataTable'
import { formatDateTime } from '@/lib/format'
import { useAuditLog } from '@/hooks/useAuditLog'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { AuditAction, AuditLogEntry } from '@/types/api'

// Partial: the backend records more actions than have labels here (alert
// rules, exports, ...) -- those fall back to their raw action name below
// rather than rendering a blank cell.
const ACTION_LABEL_KEYS: Partial<Record<AuditAction, TranslationKey>> = {
  user_created: 'auditLog.actionUserCreated',
  user_role_changed: 'auditLog.actionUserRoleChanged',
  user_password_reset: 'auditLog.actionUserPasswordReset',
  user_deleted: 'auditLog.actionUserDeleted',
  user_updated: 'auditLog.actionUserUpdated',
  user_deactivated: 'auditLog.actionUserDeactivated',
  user_activated: 'auditLog.actionUserActivated',
  user_unlocked: 'auditLog.actionUserUnlocked',
  user_sessions_revoked: 'auditLog.actionUserSessionsRevoked',
  user_password_changed: 'auditLog.actionUserPasswordChanged',
  user_totp_reset: 'auditLog.actionUserTotpReset',
  export_created: 'auditLog.actionExportCreated',
  export_downloaded: 'auditLog.actionExportDownloaded',
}

const PAGE_SIZE = 20

export function AuditLogPanel() {
  const { t } = useTranslation()
  const [offset, setOffset] = useState(0)
  const query = useAuditLog(PAGE_SIZE, offset)

  const columns = useMemo<ColumnDef<AuditLogEntry>[]>(
    () => [
      {
        accessorKey: 'created_at',
        header: t('auditLog.columnTime'),
        cell: ({ getValue }) => (
          <span className="font-data text-xs text-muted-foreground">
            {formatDateTime(getValue<string>())}
          </span>
        ),
      },
      {
        accessorKey: 'action',
        header: t('auditLog.columnAction'),
        cell: ({ getValue }) => {
          const action = getValue<AuditAction>()
          const labelKey = ACTION_LABEL_KEYS[action]
          return <span className="text-foreground">{labelKey ? t(labelKey) : action}</span>
        },
      },
      {
        accessorKey: 'actor_email',
        header: t('auditLog.columnActor'),
        cell: ({ getValue }) => <span className="font-data text-foreground">{getValue<string>()}</span>,
      },
      {
        accessorKey: 'target_email',
        header: t('auditLog.columnTarget'),
        cell: ({ getValue }) => (
          <span className="font-data text-muted-foreground">{getValue<string | null>() ?? '—'}</span>
        ),
      },
      {
        accessorKey: 'detail',
        header: t('auditLog.columnDetail'),
        cell: ({ getValue }) => (
          <span className="text-xs text-muted-foreground">{getValue<string | null>() ?? '—'}</span>
        ),
      },
    ],
    [t],
  )

  return (
    <DataTable
      columns={columns}
      data={query.data?.items ?? []}
      total={query.data?.total ?? 0}
      limit={PAGE_SIZE}
      offset={offset}
      onOffsetChange={setOffset}
      isLoading={query.isLoading}
      emptyMessage={t('auditLog.empty')}
    />
  )
}
