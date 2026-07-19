import { useEffect, useRef, useState } from 'react'

const DURATION_MS = 500

/** Animates numeric transitions on summary cards -- the only motion in the
 * UI besides the live ticker slide-in, per the "meaningful motion only" rule. */
export function useCountUp(target: number): number {
  const [display, setDisplay] = useState(target)
  const fromRef = useRef(target)
  const frameRef = useRef<number | null>(null)

  useEffect(() => {
    const from = fromRef.current
    if (from === target) return

    const start = performance.now()
    function tick(now: number) {
      const progress = Math.min(1, (now - start) / DURATION_MS)
      const eased = 1 - (1 - progress) ** 3
      setDisplay(Math.round(from + (target - from) * eased))
      if (progress < 1) {
        frameRef.current = requestAnimationFrame(tick)
      } else {
        fromRef.current = target
      }
    }
    frameRef.current = requestAnimationFrame(tick)

    return () => {
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
    }
  }, [target])

  return display
}
