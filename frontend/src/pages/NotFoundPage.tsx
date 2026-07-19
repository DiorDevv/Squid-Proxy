import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { useTranslation } from '@/i18n'

export default function NotFoundPage() {
  const { t } = useTranslation()
  return (
    <div className="flex min-h-svh flex-col items-center justify-center gap-3 bg-background text-center">
      <p className="font-data text-sm text-muted-foreground">404</p>
      <h1 className="text-lg font-semibold text-foreground">{t('notFound.heading')}</h1>
      <Button asChild variant="outline" size="sm">
        <Link to="/">{t('notFound.backToDashboard')}</Link>
      </Button>
    </div>
  )
}
