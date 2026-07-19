import type { ReactNode } from 'react'
import { cn } from '@/lib/utils'

interface PanelProps {
  title: string
  action?: ReactNode
  children: ReactNode
  className?: string
}

export function Panel({ title, action, children, className }: PanelProps) {
  return (
    <section
      className={cn(
        'flex flex-col gap-3 rounded-lg border border-border bg-card p-4 transition-colors duration-200 hover:border-primary/25',
        className,
      )}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-foreground">{title}</h2>
        {action}
      </div>
      {children}
    </section>
  )
}
