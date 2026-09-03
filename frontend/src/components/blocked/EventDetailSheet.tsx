import type { ReactNode } from 'react'
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from '@/components/ui/sheet'
import { StatusBadge } from '@/components/common/StatusBadge'
import { formatBytes, formatDateTime } from '@/lib/format'
import { useTranslation } from '@/i18n'
import type { LiveEvent } from '@/types/events'

interface EventDetailSheetProps {
  event: LiveEvent | null
  onOpenChange: (open: boolean) => void
}

function Field({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex flex-col gap-0.5 border-b border-border py-2 last:border-0">
      <span className="text-xs uppercase tracking-wide text-muted-foreground">{label}</span>
      <span className="font-data text-sm text-foreground break-all">{value ?? '—'}</span>
    </div>
  )
}

export function EventDetailSheet({ event, onOpenChange }: EventDetailSheetProps) {
  const { t } = useTranslation()

  return (
    <Sheet open={event !== null} onOpenChange={onOpenChange}>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{t('blocked.detailTitle')}</SheetTitle>
          <SheetDescription>{event?.url}</SheetDescription>
        </SheetHeader>
        {event && (
          <div className="flex flex-col px-4 pb-4">
            <Field label={t('blocked.columnTime')} value={formatDateTime(event.timestamp)} />
            <Field label={t('blocked.columnClientIp')} value={event.client_ip} />
            <Field label={t('branch.filter')} value={event.branch} />
            <Field label={t('blocked.columnUser')} value={event.user} />
            <Field label={t('blocked.detailUrl')} value={event.url} />
            <Field label={t('blocked.columnDomain')} value={event.domain} />
            <Field label={t('clientDetail.methodFilter')} value={event.method} />
            <Field label={t('blocked.columnStatus')} value={event.status_code} />
            <Field label={t('blocked.columnOutcome')} value={<StatusBadge blocked={event.blocked} />} />
            <Field label={t('blocked.detailBytes')} value={formatBytes(event.bytes)} />
            <Field
              label={t('blocked.detailDuration')}
              value={event.duration_ms != null ? `${event.duration_ms} ms` : null}
            />
            <Field label={t('blocked.detailHierarchy')} value={event.hierarchy} />
            <Field label={t('blocked.detailPeer')} value={event.peer} />
            <Field label={t('blocked.detailContentType')} value={event.content_type} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  )
}
