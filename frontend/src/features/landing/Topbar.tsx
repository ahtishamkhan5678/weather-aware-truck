import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { prefersReducedMotion } from './hooks'

const NAV = [
  { label: 'Home', href: '#top', section: 'top' },
  { label: 'Planner', to: '/planner' },
  { label: 'Method', href: '#method', section: 'method' },
  { label: 'Rules', href: '#rules', section: 'rules' },
]

function dateLine(d = new Date()) {
  const pad = (n: number) => String(n).padStart(2, '0')
  const in48 = new Date(d.getTime() + 48 * 3_600_000)
  return {
    day: d.toLocaleDateString('en-GB', { weekday: 'long' }),
    range: `${pad(d.getDate())}.${pad(d.getMonth() + 1)} – ${pad(in48.getDate())}.${pad(in48.getMonth() + 1)}`,
  }
}

/**
 * Sticky header for every viewport. A flex layout (not absolute artboard coordinates)
 * guarantees the date and CTA can never overlap; once scrolled it condenses and gains
 * frosted backgrounds so it stays legible over the light hero and the black sections.
 */
export function Topbar() {
  const bar = useRef<HTMLDivElement>(null)
  const [scrolled, setScrolled] = useState(false)
  const [active, setActive] = useState(0)
  const [hover, setHover] = useState<number | null>(null)
  const { day, range } = dateLine()

  // Condense once scrolled, and highlight the section under the upper third of the viewport.
  useEffect(() => {
    let raf = 0
    const update = () => {
      setScrolled(window.scrollY > 24)
      const probe = window.innerHeight * 0.35
      let current = 0
      NAV.forEach((n, i) => {
        const el = n.section ? document.getElementById(n.section) : null
        if (el && el.getBoundingClientRect().top <= probe) current = i
      })
      setActive(current)
    }
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(update)
    }
    update()
    window.addEventListener('scroll', onScroll, { passive: true })
    window.addEventListener('resize', onScroll)
    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('scroll', onScroll)
      window.removeEventListener('resize', onScroll)
    }
  }, [])

  useEffect(() => {
    if (prefersReducedMotion() || !bar.current) return
    bar.current.animate([{ opacity: 0, transform: 'translateY(-16px)' }, { opacity: 1, transform: 'none' }], {
      duration: 800,
      easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
      fill: 'both',
    })
  }, [])

  const pill = hover ?? active

  return (
    <div className={`topbar${scrolled ? ' is-scrolled' : ''}`}>
      <div className="topbar__inner" ref={bar}>
        <nav className="nav" aria-label="Primary" onMouseLeave={() => setHover(null)}>
          <span className="nav__pill" style={{ transform: `translateX(calc(${pill} * var(--nav-item)))` }} />
          {NAV.map((n, i) =>
            n.to ? (
              <Link key={n.label} to={n.to} className={pill === i ? 'is-active' : ''} onMouseEnter={() => setHover(i)}>
                {n.label}
              </Link>
            ) : (
              <a key={n.label} href={n.href} className={pill === i ? 'is-active' : ''} onMouseEnter={() => setHover(i)}>
                {n.label}
              </a>
            ),
          )}
        </nav>
        <div className="topbar__right">
          <div className="topbar__date">
            <span>{day}</span> / {range} · 48h forecast
          </div>
          <Link to="/planner" className="btn-black topbar__cta" aria-label="Plan a route">
            <span className="topbar__cta-text">Plan Route</span> <span aria-hidden>↗</span>
          </Link>
        </div>
      </div>
    </div>
  )
}
