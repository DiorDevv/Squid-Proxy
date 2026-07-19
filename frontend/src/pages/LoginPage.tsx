import { useState } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import { Radar, TriangleAlert } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/lib/auth-store'
import { ApiError } from '@/lib/api-client'
import { useTranslation } from '@/i18n'

export default function LoginPage() {
  const { t } = useTranslation()
  const { login } = useAuth()
  const status = useAuthStore((state) => state.status)
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      await login(email, password)
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('login.genericError'))
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="relative flex min-h-svh items-center justify-center overflow-hidden bg-background px-4">
      {/* Ambient glow -- purely decorative background wash, kept subtle and
          fixed so it never competes with the form content above it. */}
      <div
        className="gradient-warning pointer-events-none absolute top-1/4 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full opacity-[0.08] blur-[100px]"
        aria-hidden="true"
      />
      <div className="relative w-full max-w-sm animate-in fade-in slide-in-from-bottom-2 duration-300">
        <div className="mb-8 flex flex-col items-center gap-3">
          <div className="gradient-warning flex h-11 w-11 items-center justify-center rounded-xl shadow-[0_0_24px_-6px_var(--warning)]">
            <Radar className="h-5 w-5 text-white" aria-hidden="true" />
          </div>
          <h1 className="text-gradient-brand text-lg font-bold">{t('login.brand')}</h1>
          <p className="text-sm text-muted-foreground">{t('login.tagline')}</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4 rounded-lg border border-border bg-card p-6 shadow-xl">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="email">{t('login.email')}</Label>
            <Input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={submitting}
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="password">{t('login.password')}</Label>
            <Input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
            />
          </div>

          {error && (
            <div
              role="alert"
              className="flex animate-in items-center gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive fade-in slide-in-from-top-1 duration-200"
            >
              <TriangleAlert className="h-4 w-4 shrink-0" aria-hidden="true" />
              {error}
            </div>
          )}

          <Button type="submit" disabled={submitting} className="mt-2">
            {submitting ? t('login.signingIn') : t('login.signIn')}
          </Button>
        </form>
      </div>
    </div>
  )
}
