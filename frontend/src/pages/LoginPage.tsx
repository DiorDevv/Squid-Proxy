import { useEffect, useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import { Navigate, useNavigate } from 'react-router-dom'
import {
  Activity,
  BellRing,
  Eye,
  EyeOff,
  KeyRound,
  Loader2,
  Radar,
  ShieldCheck,
  TriangleAlert,
} from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { useAuth } from '@/hooks/useAuth'
import { useAuthStore } from '@/lib/auth-store'
import { ApiError } from '@/lib/api-client'
import { useTranslation, type TranslationKey } from '@/i18n'

const HERO_FEATURES: { icon: typeof Activity; label: TranslationKey }[] = [
  { icon: Activity, label: 'login.featureRealtime' },
  { icon: BellRing, label: 'login.featureAlerts' },
  { icon: ShieldCheck, label: 'login.featureCompliance' },
]

// Backend's LOGIN_RATE_LIMIT window is 5/minute; we don't get the exact
// remaining time back from a 429, so re-enable the form after a fixed
// cooldown comfortably inside that window rather than leaving it disabled
// until a full page reload.
const RATE_LIMIT_COOLDOWN_SECONDS = 30

export default function LoginPage() {
  const { t } = useTranslation()
  const { login, completeMfaLogin } = useAuth()
  const status = useAuthStore((state) => state.status)
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [capsLockOn, setCapsLockOn] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [errorKey, setErrorKey] = useState(0)
  const [retryIn, setRetryIn] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const formRef = useRef<HTMLFormElement>(null)
  // Set once login() reports the account has 2FA on -- switches the form
  // to the code-entry step instead of navigating straight in. Null means
  // "still on the email/password step".
  const [mfaChallengeToken, setMfaChallengeToken] = useState<string | null>(null)
  const [mfaCode, setMfaCode] = useState('')

  useEffect(() => {
    if (retryIn <= 0) return
    const timer = window.setInterval(() => {
      setRetryIn((prev) => Math.max(0, prev - 1))
    }, 1000)
    return () => window.clearInterval(timer)
  }, [retryIn])

  // Retrigger the shake without remounting the form (a `key`-based remount
  // used to reset `autoFocus` on the email input back to the top on every
  // failed attempt, stealing focus away from the password field).
  useEffect(() => {
    if (errorKey === 0) return
    const form = formRef.current
    if (!form) return
    form.classList.remove('animate-shake')
    void form.offsetWidth // force reflow so re-adding the class replays the animation
    form.classList.add('animate-shake')
  }, [errorKey])

  if (status === 'authenticated') {
    return <Navigate to="/" replace />
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const challengeToken = await login(email.trim(), password)
      if (challengeToken) {
        setMfaChallengeToken(challengeToken)
        return
      }
      navigate('/', { replace: true })
    } catch (err) {
      if (err instanceof ApiError && err.status === 429) {
        setRetryIn(RATE_LIMIT_COOLDOWN_SECONDS)
        setError(t('login.rateLimitedError'))
      } else {
        setError(err instanceof ApiError ? err.message : t('login.genericError'))
      }
      // Re-triggers the shake animation even if the same error string
      // appears twice in a row (React won't replay a keyed animation
      // unless something about the element actually changes).
      setErrorKey((prev) => prev + 1)
    } finally {
      setSubmitting(false)
    }
  }

  async function handleMfaSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!mfaChallengeToken) return
    setError(null)
    setSubmitting(true)
    try {
      await completeMfaLogin(mfaChallengeToken, mfaCode.trim())
      navigate('/', { replace: true })
    } catch (err) {
      setError(err instanceof ApiError ? err.message : t('login.genericError'))
      setErrorKey((prev) => prev + 1)
      setMfaCode('')
    } finally {
      setSubmitting(false)
    }
  }

  function handleBackToPassword() {
    setMfaChallengeToken(null)
    setMfaCode('')
    setError(null)
  }

  function trackCapsLock(e: KeyboardEvent<HTMLInputElement>) {
    if (typeof e.getModifierState === 'function') {
      setCapsLockOn(e.getModifierState('CapsLock'))
    }
  }

  return (
    <div className="flex min-h-svh bg-background">
      {/* Brand / value-proposition panel -- hidden below lg, where the
          form alone (with its own compact brand mark) is all there's
          room for. */}
      <div className="relative hidden w-full max-w-md flex-col justify-between overflow-hidden bg-[#0a0e18] p-10 lg:flex xl:max-w-lg">
        <div className="bg-grid-pattern pointer-events-none absolute inset-0 text-white opacity-[0.06]" aria-hidden="true" />
        <div
          className="gradient-warning pointer-events-none absolute -top-24 -left-24 h-72 w-72 rounded-full opacity-20 blur-[100px]"
          aria-hidden="true"
        />
        <div
          className="gradient-purple pointer-events-none absolute -right-24 -bottom-24 h-72 w-72 rounded-full opacity-20 blur-[100px]"
          aria-hidden="true"
        />

        <div className="relative flex items-center gap-2.5">
          <div className="gradient-warning flex h-9 w-9 items-center justify-center rounded-lg shadow-[0_0_24px_-6px_var(--warning)]">
            <Radar className="h-4.5 w-4.5 text-white" aria-hidden="true" />
          </div>
          <span className="text-gradient-brand text-base font-bold">{t('login.brand')}</span>
        </div>

        <div className="relative flex flex-col gap-6">
          <h2 className="max-w-sm text-2xl leading-snug font-semibold text-white">{t('login.heroTitle')}</h2>
          <ul className="flex flex-col gap-4">
            {HERO_FEATURES.map(({ icon: Icon, label }) => (
              <li key={label} className="flex items-center gap-3 text-sm text-white/70">
                <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-white/5 ring-1 ring-white/10">
                  <Icon className="h-4 w-4 text-white/80" aria-hidden="true" />
                </span>
                {t(label)}
              </li>
            ))}
          </ul>
        </div>

        <p className="relative text-xs text-white/40">{t('login.heroFooter')}</p>
      </div>

      {/* Form panel */}
      <div className="relative flex flex-1 items-center justify-center overflow-hidden px-4 py-12">
        <div
          className="gradient-warning pointer-events-none absolute top-1/4 left-1/2 h-64 w-64 -translate-x-1/2 rounded-full opacity-[0.08] blur-[100px] lg:hidden"
          aria-hidden="true"
        />
        <div className="relative w-full max-w-sm animate-in fade-in slide-in-from-bottom-2 duration-300">
          <div className="mb-8 flex flex-col items-center gap-3 lg:hidden">
            <div className="gradient-warning flex h-11 w-11 items-center justify-center rounded-xl shadow-[0_0_24px_-6px_var(--warning)]">
              <Radar className="h-5 w-5 text-white" aria-hidden="true" />
            </div>
            <h1 className="text-gradient-brand text-lg font-bold">{t('login.brand')}</h1>
            <p className="text-sm text-muted-foreground">{t('login.tagline')}</p>
          </div>

          <div className="mb-6 hidden flex-col gap-1 lg:flex">
            <h1 className="text-xl font-semibold text-foreground">{t('login.welcomeBack')}</h1>
            <p className="text-sm text-muted-foreground">{t('login.tagline')}</p>
          </div>

          {mfaChallengeToken ? (
            <form
              ref={formRef}
              onSubmit={handleMfaSubmit}
              className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6 shadow-xl"
            >
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center gap-2 text-foreground">
                  <KeyRound className="h-4 w-4 shrink-0" aria-hidden="true" />
                  <h2 className="text-sm font-semibold">{t('login.mfaTitle')}</h2>
                </div>
                <p className="text-xs text-muted-foreground">{t('login.mfaHint')}</p>
              </div>
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="mfa-code">{t('login.mfaCodeLabel')}</Label>
                <Input
                  id="mfa-code"
                  type="text"
                  inputMode="text"
                  autoComplete="one-time-code"
                  autoFocus
                  required
                  value={mfaCode}
                  onChange={(e) => setMfaCode(e.target.value)}
                  disabled={submitting}
                  aria-invalid={Boolean(error)}
                  className="font-data text-center tracking-[0.3em]"
                  placeholder="000000"
                />
              </div>

              {error && (
                <div
                  role="alert"
                  className="flex animate-in items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive fade-in slide-in-from-top-1 duration-200"
                >
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{error}</span>
                </div>
              )}

              <Button type="submit" disabled={submitting} className="mt-2 gap-2">
                {submitting && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {submitting ? t('login.signingIn') : t('login.mfaVerify')}
              </Button>

              <button
                type="button"
                onClick={handleBackToPassword}
                disabled={submitting}
                className="text-center text-xs text-muted-foreground underline-offset-2 hover:text-foreground hover:underline"
              >
                {t('login.mfaBack')}
              </button>
            </form>
          ) : (
            <form
              ref={formRef}
              onSubmit={handleSubmit}
              className="flex flex-col gap-4 rounded-xl border border-border bg-card p-6 shadow-xl"
            >
              <div className="flex flex-col gap-1.5">
                <Label htmlFor="email">{t('login.email')}</Label>
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  autoFocus
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  disabled={submitting}
                  aria-invalid={Boolean(error)}
                />
              </div>
              <div className="flex flex-col gap-1.5">
                <div className="flex items-center justify-between">
                  <Label htmlFor="password">{t('login.password')}</Label>
                  {capsLockOn && (
                    <span className="flex items-center gap-1 text-xs text-warning">
                      <TriangleAlert className="h-3 w-3" aria-hidden="true" />
                      {t('login.capsLockOn')}
                    </span>
                  )}
                </div>
                <div className="relative">
                  <Input
                    id="password"
                    type={showPassword ? 'text' : 'password'}
                    autoComplete="current-password"
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    onKeyDown={trackCapsLock}
                    onKeyUp={trackCapsLock}
                    disabled={submitting}
                    aria-invalid={Boolean(error)}
                    className="pr-9"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((prev) => !prev)}
                    tabIndex={-1}
                    className="absolute inset-y-0 right-0 flex w-9 items-center justify-center text-muted-foreground transition-colors hover:text-foreground"
                    aria-label={showPassword ? t('login.hidePassword') : t('login.showPassword')}
                  >
                    {showPassword ? (
                      <EyeOff className="h-4 w-4" aria-hidden="true" />
                    ) : (
                      <Eye className="h-4 w-4" aria-hidden="true" />
                    )}
                  </button>
                </div>
              </div>

              {error && (
                <div
                  role="alert"
                  className="flex animate-in items-start gap-2 rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive fade-in slide-in-from-top-1 duration-200"
                >
                  <TriangleAlert className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" />
                  <span>{error}</span>
                </div>
              )}

              <Button type="submit" disabled={submitting || retryIn > 0} className="mt-2 gap-2">
                {submitting && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
                {submitting
                  ? t('login.signingIn')
                  : retryIn > 0
                    ? t('login.tryAgainIn', { seconds: retryIn })
                    : t('login.signIn')}
              </Button>

              <p className="text-center text-xs text-muted-foreground">{t('login.noAccountNote')}</p>
            </form>
          )}

          <div className="mt-6 flex items-center justify-center gap-1.5 text-xs text-muted-foreground">
            <ShieldCheck className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
            {t('login.securityNote')}
          </div>
        </div>
      </div>
    </div>
  )
}
