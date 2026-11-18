import { useEffect, useRef, useState } from 'react'

export const prefersReducedMotion = () =>
  typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches

/** `?rec=1` → the page is captured in one frame, so scroll-driven effects run on a timer. */
export const isRecording = () => typeof window !== 'undefined' && new URLSearchParams(window.location.search).get('rec') === '1'

export function useInView<T extends Element>(threshold = 0.3) {
  const ref = useRef<T>(null)
  const [inView, setInView] = useState(false)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    const io = new IntersectionObserver(
      ([e]) => {
        if (e.isIntersecting) {
          setInView(true)
          io.disconnect()
        }
      },
      { threshold },
    )
    io.observe(el)
    return () => io.disconnect()
  }, [threshold])
  return [ref, inView] as const
}

/** Counts from 0 to `target` (ease-out) once `start` becomes true. */
export function useCountUp(target: number, start: boolean, durationMs = 1400, delayMs = 0) {
  const [value, setValue] = useState(prefersReducedMotion() ? target : 0)
  useEffect(() => {
    if (!start || prefersReducedMotion()) return
    let raf = 0
    const t0 = performance.now() + delayMs
    const tick = (now: number) => {
      const p = Math.min(1, Math.max(0, (now - t0) / durationMs))
      setValue(Math.round(target * (1 - Math.pow(1 - p, 3))))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, start, durationMs, delayMs])
  return value
}
