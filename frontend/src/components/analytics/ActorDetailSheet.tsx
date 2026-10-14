import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { ActorActions, ActorInsights } from '@/components/analytics/ActorInsights'
import { useTranslation } from '@/i18n'
import type { ActorRow } from '@/types/api'

interface ActorDetailSheetProps {
  actor: ActorRow | null
  rangeParams: Record<string, string>
  onOpenChange: (open: boolean) => void
}

export function ActorDetailSheet({ actor, rangeParams, onOpenChange }: ActorDetailSheetProps) {
  const { t } = useTranslation()

  return (
    <Sheet open={actor !== null} onOpenChange={onOpenChange}>
      {/* Widened from max-w-lg -- five stat cards plus nested category/domain
          rows need real room; at the old width everything was cramped
          two-per-line with truncated labels. */}
      <SheetContent className="flex w-full flex-col data-[side=right]:sm:max-w-2xl">
        <SheetHeader>
          <div className="flex items-start justify-between gap-2">
            <div className="min-w-0">
              <SheetTitle className="font-data text-lg break-all">{actor?.actor}</SheetTitle>
              <SheetDescription>
                {actor?.is_user ? t('analytics.who.colUser') : t('analytics.who.colClientIp')}
              </SheetDescription>
            </div>
            {actor && <ActorActions actor={actor.actor} isUser={actor.is_user} branch={rangeParams.branch} />}
          </div>
        </SheetHeader>

        <div className="flex flex-1 flex-col gap-6 overflow-y-auto px-4 pb-8">
          {actor && <ActorInsights actor={actor.actor} isUser={actor.is_user} rangeParams={rangeParams} />}
        </div>
      </SheetContent>
    </Sheet>
  )
}
