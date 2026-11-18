import { useEffect, useRef } from 'react'
import { isRecording, prefersReducedMotion } from './hooks'

const LINES = [
  'We believe the safest route is',
  'not always the shortest. Every mile',
  'is scored against the forecast at the',
  'hour the truck arrives, so drivers move',
  'freight without guessing the sky.',
]
const SOFT_EDGE = 3 // words
let counter = 0
const WORDS = LINES.map((line) => line.split(' ').map((word) => ({ word, index: counter++ })))

/** Words fill from grey to white in reading order as the section scrolls through. */
export function Statement() {
  const section = useRef<HTMLElement>(null)
  const words = useRef<HTMLSpanElement[]>([])

  useEffect(() => {
    const el = section.current
    if (!el) return
    const spans = words.current
    const paint = (progress: number) => {
      const lit = progress * (spans.length + SOFT_EDGE)
      spans.forEach((w, i) => {
        const t = Math.max(0, Math.min(1, (lit - i) / SOFT_EDGE))
        w.style.setProperty('--fill', t.toFixed(3))
      })
    }
    if (prefersReducedMotion()) return paint(1)
    if (isRecording()) {
      const t0 = performance.now()
      let raf = 0
      const tick = (now: number) => {
        const p = Math.min(1, Math.max(0, (now - t0 - 1300) / 2900)) // 1.3 → 4.2 s
        paint(p)
        if (p < 1) raf = requestAnimationFrame(tick)
      }
      raf = requestAnimationFrame(tick)
      return () => cancelAnimationFrame(raf)
    }
    let raf = 0
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const r = el.getBoundingClientRect()
        const vh = window.innerHeight
        paint(Math.max(0, Math.min(1, (vh * 0.85 - r.top) / (r.height * 0.75))))
      })
    }
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
      cancelAnimationFrame(raf)
    }
  }, [])

  return (
    <section className="statement" id="method" ref={section}>
      <p className="statement__text">
        {WORDS.map((line, li) => (
          <span key={li} className="statement__line">
            {line.map(({ word, index }) => (
              <span
                key={index}
                className="word"
                ref={(n) => {
                  if (n) words.current[index] = n
                }}
              >
                {word}{' '}
              </span>
            ))}
          </span>
        ))}
      </p>
      <p className="statement__sub">
        Weather, load and time — weighed together.
        <br />
        <span>Built for drivers who cannot afford a bad call.</span>
      </p>
    </section>
  )
}
