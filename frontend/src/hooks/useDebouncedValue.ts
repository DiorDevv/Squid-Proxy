import { useEffect, useState } from 'react'

/** Delays reflecting `value` until it's been stable for `delayMs`, so a
 * fast typist doesn't fire one server request per keystroke. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value)

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs)
    return () => clearTimeout(timer)
  }, [value, delayMs])

  return debounced
}
