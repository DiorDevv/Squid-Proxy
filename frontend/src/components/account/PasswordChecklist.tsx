import { Check, X } from 'lucide-react'
import { checkPassword, PASSWORD_MIN_LENGTH, type PasswordRule } from '@/lib/password-policy'
import { cn } from '@/lib/utils'
import { useTranslation, type TranslationKey } from '@/i18n'

const RULE_KEYS: Record<PasswordRule, TranslationKey> = {
  length: 'passwordPolicy.length',
  classes: 'passwordPolicy.classes',
  noUsername: 'passwordPolicy.noUsername',
  noCommon: 'passwordPolicy.noCommon',
  variety: 'passwordPolicy.variety',
}

/** Live hints mirroring the server-side policy (lib/password-policy.ts). */
export function PasswordChecklist({ password, username }: { password: string; username: string }) {
  const { t } = useTranslation()
  const results = checkPassword(password, username)

  return (
    <ul className="flex flex-col gap-1" aria-label={t('passwordPolicy.title')}>
      {(Object.keys(RULE_KEYS) as PasswordRule[]).map((rule) => {
        const ok = results[rule]
        const Icon = ok ? Check : X
        return (
          <li
            key={rule}
            className={cn(
              'flex items-center gap-1.5 text-xs transition-colors',
              ok ? 'text-success' : 'text-muted-foreground',
            )}
          >
            <Icon className="h-3 w-3 shrink-0" aria-hidden="true" />
            <span>{t(RULE_KEYS[rule], { min: PASSWORD_MIN_LENGTH })}</span>
            <span className="sr-only">
              {ok ? t('passwordPolicy.met') : t('passwordPolicy.notMet')}
            </span>
          </li>
        )
      })}
    </ul>
  )
}
