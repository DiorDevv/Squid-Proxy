/**
 * Client-side mirror of backend app/core/password_policy.py, for live
 * hints while typing. The server stays the authority -- it re-checks
 * every password and also enforces the no-reuse history this can't see.
 */
export const PASSWORD_MIN_LENGTH = 12
export const PASSWORD_HISTORY = 5
export const USERNAME_PATTERN = /^[a-z0-9][a-z0-9._-]{2,63}$/

const COMMON = [
  'password',
  'parol',
  'qwerty',
  '123456',
  '111111',
  'abc123',
  'letmein',
  'welcome',
  'iloveyou',
  'admin123',
  'p@ssw0rd',
  'squid',
]

export type PasswordRule = 'length' | 'classes' | 'noUsername' | 'noCommon' | 'variety'

export function checkPassword(password: string, username = ''): Record<PasswordRule, boolean> {
  const lowered = password.toLowerCase()
  const classes = [/[a-z]/, /[A-Z]/, /[0-9]/, /[^A-Za-z0-9]/].filter((re) =>
    re.test(password),
  ).length
  return {
    length: password.length >= PASSWORD_MIN_LENGTH,
    classes: classes >= 3,
    noUsername: username.length < 3 || !lowered.includes(username.toLowerCase()),
    noCommon: !COMMON.some((word) => lowered.includes(word)),
    variety: new Set(password).size >= 6,
  }
}

export function passwordAcceptable(password: string, username = ''): boolean {
  return Object.values(checkPassword(password, username)).every(Boolean)
}
