import { useMemo, useState } from 'react'
import type { ColumnDef } from '@tanstack/react-table'
import { DataTable } from '@/components/common/DataTable'
import { formatDateTime } from '@/lib/format'
import { useAuditLog } from '@/hooks/useAuditLog'
import { useTranslation, type TranslationKey } from '@/i18n'
import type { AuditAction, AuditLogEntry } from '@/types/api'

const ACTION_LABEL_KEYS: Record<AuditAction, TranslationKey> = {
  user_created: 'auditLog.actionUserCreated',
  user_role_changed: 'auditLog.actionUserRoleChanged',
  user_password_reset: 'auditLog.actionUserPasswordReset',
  user_deleted: 'auditLog.actionUserDeleted',
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
        cell: ({ getValue }) => <span className="text-foreground">{t(ACTION_LABEL_KEYS[getValue<AuditAction>()])}</span>,
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
