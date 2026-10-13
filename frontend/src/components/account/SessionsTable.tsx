import { LogOut } from 'lucide-react'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { formatDateTime, formatRelativeTime } from '@/lib/format'
import { describeUserAgent } from '@/lib/user-agent'
import { useTranslation } from '@/i18n'
import type { SessionInfo } from '@/types/auth'

interface SessionsTableProps {
  sessions: SessionInfo[]
  onRevoke: (sessionId: string) => void
  revoking: boolean
}

/** Shared by the profile page (own sessions) and the admin's per-user
 * sessions dialog. The current session can't be ended from here -- that's
 * what signing out is for. */
export function SessionsTable({ sessions, onRevoke, revoking }: SessionsTableProps) {
  const { t } = useTranslation()

  if (sessions.length === 0) {
    return <p className="text-sm text-muted-foreground">{t('sessions.empty')}</p>
  }

  return (
    <Table>
      <TableHeader>
        <TableRow className="hover:bg-transparent">
          <TableHead>{t('sessions.device')}</TableHead>
          <TableHead>{t('sessions.ip')}</TableHead>
          <TableHead>{t('sessions.started')}</TableHead>
          <TableHead>{t('sessions.lastSeen')}</TableHead>
          <TableHead className="text-right">
            <span className="sr-only">{t('userManagement.columnActions')}</span>
          </TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {sessions.map((session) => (
          <TableRow key={session.id}>
            <TableCell>
              <div className="flex items-center gap-2">
                <span className="text-foreground" title={session.user_agent ?? undefined}>
                  {describeUserAgent(session.user_agent)}
                </span>
                {session.current && (
                  <Badge variant="outline" className="text-[10px]">
                    {t('sessions.current')}
                  </Badge>
                )}
              </div>
            </TableCell>
            <TableCell>
              <span className="font-data text-xs text-muted-foreground">{session.ip ?? '—'}</span>
            </TableCell>
            <TableCell>
              <span className="font-data text-xs text-muted-foreground">
                {session.started_at ? formatDateTime(session.started_at) : '—'}
              </span>
            </TableCell>
            <TableCell>
              <span className="font-data text-xs text-muted-foreground">
                {formatRelativeTime(session.last_seen_at)}
              </span>
            </TableCell>
            <TableCell className="text-right">
              {!session.current && (
                <Button
                  variant="outline"
                  size="icon-sm"
                  onClick={() => onRevoke(session.id)}
                  disabled={revoking}
                  aria-label={t('sessions.end')}
                  title={t('sessions.end')}
                >
                  <LogOut className="h-3.5 w-3.5 text-destructive" />
                </Button>
              )}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  )
}
