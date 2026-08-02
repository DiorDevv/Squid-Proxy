import { useLayoutEffect, useRef, useState } from 'react'
import { CalendarRange } from 'lucide-react'
import { cn } from '@/lib/utils'
import { RANGE_OPTIONS } from '@/lib/constants'
import { useFiltersStore } from '@/lib/filters-store'
import { Button } from '@/components/ui/button'
import { Label } from '@/components/ui/label'
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover'
import { toDatetimeLocalValue } from '@/lib/format'
import { useTranslation } from '@/i18n'

const CUSTOM_KEY = 'custom'

export function RangeSelector() {
  const { t } = useTranslation()
  const range = useFiltersStore((state) => state.range)
  const mode = useFiltersStore((state) => state.mode)
  const customFrom = useFiltersStore((state) => state.customFrom)
  const customTo = useFiltersStore((state) => state.customTo)
  const setRange = useFiltersStore((state) => state.setRange)
  const setCustomRange = useFiltersStore((state) => state.setCustomRange)

  const [open, setOpen] = useState(false)
  const [draftFrom, setDraftFrom] = useState(() => toDatetimeLocalValue(new Date(Date.now() - 24 * 60 * 60 * 1000)))
  const [draftTo, setDraftTo] = useState(() => toDatetimeLocalValue(new Date()))
  const [error, setError] = useState<string | null>(null)

  const activeKey = mode === 'custom' ? CUSTOM_KEY : range
  const buttonRefs = useRef<Record<string, HTMLButtonElement | null>>({})
  const [indicator, setIndicator] = useState<{ left: number; width: number } | null>(null)

  // Measures the active segment after every render (layout, not paint) so
  // the sliding pill never flashes at the wrong spot on mount or on range
  // change -- a plain useEffect would show one stale frame first.
  useLayoutEffect(() => {
    const activeButton = buttonRefs.current[activeKey]
    if (activeButton) {
      setIndicator({ left: activeButton.offsetLeft, width: activeButton.offsetWidth })
    }
  }, [activeKey])

  function handleApply() {
    if (!draftFrom || !draftTo) {
      setError(t('common.rangeIncomplete'))
      return
    }
    const from = new Date(draftFrom)
    const to = new Date(draftTo)
    if (Number.isNaN(from.getTime()) || Number.isNaN(to.getTime())) {
      setError(t('common.rangeIncomplete'))
      return
    }
    if (from >= to) {
      setError(t('common.rangeInvalidOrder'))
      return
    }
    setError(null)
    setCustomRange(from.toISOString(), to.toISOString())
    setOpen(false)
  }

  return (
    <div
      className="relative inline-flex items-center rounded-md border border-border bg-secondary/50 p-0.5"
      role="group"
      aria-label={t('topbar.timeRange')}
    >
      {/* Single shared "active" pill that slides/resizes between segments,
          instead of each button independently toggling its own background --
          this is what makes the switch read as one continuous motion. */}
      {indicator && (
        <div
          className="gradient-warning pointer-events-none absolute top-0.5 bottom-0.5 rounded-[calc(var(--radius-sm)-2px)] shadow-[0_0_12px_-4px_var(--warning)] transition-[left,width] duration-300 ease-out"
          style={{ left: indicator.left, width: indicator.width }}
          aria-hidden="true"
        />
      )}
      {RANGE_OPTIONS.map((option) => (
        <button
          key={option.value}
          ref={(el) => {
            buttonRefs.current[option.value] = el
          }}
          type="button"
          onClick={() => setRange(option.value)}
          aria-pressed={mode === 'preset' && range === option.value}
          className={cn(
            'font-data relative z-10 rounded-[calc(var(--radius-sm)-2px)] px-2.5 py-1 text-xs font-medium transition-colors duration-200',
            mode === 'preset' && range === option.value
              ? 'text-primary-foreground'
              : 'text-muted-foreground hover:text-foreground',
          )}
        >
          {option.label}
        </button>
      ))}
      <Popover
        open={open}
        onOpenChange={(next) => {
          setOpen(next)
          if (next) {
            setError(null)
            // Reload the draft from the currently active custom range (if
            // any) every time the popover opens -- otherwise these fields
            // kept showing whatever default they had on first mount, so
            // reopening to tweak an already-applied custom range silently
            // offered to replace it with that stale default instead of the
            // range actually in effect.
            setDraftFrom(
              mode === 'custom' && customFrom
                ? toDatetimeLocalValue(new Date(customFrom))
                : toDatetimeLocalValue(new Date(Date.now() - 24 * 60 * 60 * 1000)),
            )
            setDraftTo(
              mode === 'custom' && customTo
                ? toDatetimeLocalValue(new Date(customTo))
                : toDatetimeLocalValue(new Date()),
            )
          }
        }}
      >
        <PopoverTrigger asChild>
          <button
            ref={(el) => {
              buttonRefs.current[CUSTOM_KEY] = el
            }}
            type="button"
            aria-pressed={mode === 'custom'}
            className={cn(
              'relative z-10 flex items-center gap-1 rounded-[calc(var(--radius-sm)-2px)] px-2.5 py-1 text-xs font-medium transition-colors duration-200',
              mode === 'custom' ? 'text-primary-foreground' : 'text-muted-foreground hover:text-foreground',
            )}
          >
            <CalendarRange className="h-3.5 w-3.5" aria-hidden="true" />
            {t('common.custom')}
          </button>
        </PopoverTrigger>
        <PopoverContent align="end" className="flex flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="range-from">{t('common.from')}</Label>
            <input
              id="range-from"
              type="datetime-local"
              value={draftFrom}
              onChange={(e) => {
                setDraftFrom(e.target.value)
                setError(null)
              }}
              className="font-data h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground transition-all duration-150 outline-none hover:border-ring/40 focus-visible:border-ring focus-visible:shadow-[0_0_16px_-6px_var(--ring)]"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="range-to">{t('common.to')}</Label>
            <input
              id="range-to"
              type="datetime-local"
              value={draftTo}
              onChange={(e) => {
                setDraftTo(e.target.value)
                setError(null)
              }}
              className="font-data h-8 rounded-md border border-input bg-background px-2 text-xs text-foreground transition-all duration-150 outline-none hover:border-ring/40 focus-visible:border-ring focus-visible:shadow-[0_0_16px_-6px_var(--ring)]"
            />
          </div>
          {error && (
            <p className="text-xs text-destructive" role="alert">
              {error}
            </p>
          )}
          <Button size="sm" onClick={handleApply}>
            {t('common.apply')}
          </Button>
        </PopoverContent>
      </Popover>
    </div>
  )
}
