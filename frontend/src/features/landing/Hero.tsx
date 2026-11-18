import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { isRecording, prefersReducedMotion, useCountUp } from './hooks'

const NAV = [
  { label: 'Home', href: '#top' },
  { label: 'Planner', to: '/planner' },
  { label: 'Method', href: '#method' },
  { label: 'Rules', href: '#rules' },
]

const MARKS = [
  { name: '10 mi', glyph: 'M2 10h16M6 6v8M14 6v8' },
  { name: '25 mi', glyph: 'M3 15 10 4l7 11z' },
  { name: '50 mi', glyph: 'M10 3a7 7 0 1 0 0 14 7 7 0 0 0 0-14z' },
  { name: 'Wind', glyph: 'M2 7h11a3 3 0 1 0-3-3M2 13h14a3 3 0 1 1-3 3' },
  { name: 'Rain', glyph: 'M10 3c3 4 5 7 5 9a5 5 0 0 1-10 0c0-2 2-5 5-9z' },
  { name: 'Snow', glyph: 'M10 2v16M3 6l14 8M17 6 3 14' },
]

function dateLine(d = new Date()) {
  const day = d.toLocaleDateString('en-GB', { weekday: 'long' })
  const dm = `${String(d.getDate()).padStart(2, '0')}.${String(d.getMonth() + 1).padStart(2, '0')}`
  const in48 = new Date(d.getTime() + 48 * 3_600_000)
  const end = `${String(in48.getDate()).padStart(2, '0')}.${String(in48.getMonth() + 1).padStart(2, '0')}`
  return { day, range: `${dm} – ${end} · 48h forecast` }
}

export function Hero() {
  const root = useRef<HTMLElement>(null)
  const photo = useRef<HTMLDivElement>(null)
  const [navIndex, setNavIndex] = useState(0)
  const [hoverIndex, setHoverIndex] = useState<number | null>(null)
  const [loaded, setLoaded] = useState(false)
  const routes = useCountUp(3, loaded, 1400, 500)
  const hours = useCountUp(48, loaded, 1400, 600)
  const { day, range } = dateLine()

  // Load choreography (Web Animations API).
  useEffect(() => {
    const el = root.current
    if (!el) return
    setLoaded(true)
    if (prefersReducedMotion()) return
    const ease = 'cubic-bezier(0.22, 1, 0.36, 1)'
    el.querySelectorAll<HTMLElement>('.title-line > span').forEach((s, i) =>
      s.animate([{ transform: 'translateY(105%)' }, { transform: 'translateY(0)' }], { duration: 1000, delay: 150 + i * 110, easing: ease, fill: 'both' }),
    )
    el.querySelector('.hero__photo img')?.animate(
      [
        { opacity: 0, transform: 'translateY(40px)', filter: 'blur(14px) grayscale(1)' },
        { opacity: 1, transform: 'translateY(0)', filter: 'blur(0) grayscale(1)' },
      ],
      { duration: 1300, easing: ease, fill: 'both' },
    )
    el.querySelector('.nav')?.animate([{ opacity: 0, transform: 'translateY(-16px)' }, { opacity: 1, transform: 'none' }], { duration: 800, easing: ease, fill: 'both' })
    el.querySelectorAll<HTMLElement>('[data-rise]').forEach((n, i) =>
      n.animate([{ opacity: 0, transform: 'translateY(14px)' }, { opacity: 1, transform: 'none' }], { duration: 800, delay: 300 + i * 55, easing: ease, fill: 'both' }),
    )
    el.querySelector('.outnow__progress i')?.animate([{ transform: 'scaleX(0)' }, { transform: 'scaleX(1)' }], { duration: 1600, delay: 900, easing: ease, fill: 'both' })
  }, [])

  // Photo drifts at 0.12× scroll (or slowly on its own while recording).
  useEffect(() => {
    if (prefersReducedMotion()) return
    const img = photo.current
    if (!img) return
    if (isRecording()) {
      const a = img.animate([{ transform: 'translateY(0)' }, { transform: 'translateY(40px)' }], { duration: 8000, fill: 'both', easing: 'linear' })
      return () => a.cancel()
    }
    let raf = 0
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        img.style.transform = `translate3d(0, ${window.scrollY * 0.12}px, 0)`
      })
    }
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      window.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(raf)
    }
  }, [])

  const pillIndex = hoverIndex ?? navIndex

  return (
    <header className="hero" id="top" ref={root}>
      <div className="hero__photo" ref={photo} aria-hidden>
        <img src="/media/hero-road.jpg" alt="" fetchPriority="high" />
      </div>

      <nav className="nav" aria-label="Primary" onMouseLeave={() => setHoverIndex(null)}>
        <span className="nav__pill" style={{ transform: `translateX(calc(${pillIndex} * var(--nav-item)))` }} />
        {NAV.map((n, i) =>
          n.to ? (
            <Link key={n.label} to={n.to} className={pillIndex === i ? 'is-active' : ''} onMouseEnter={() => setHoverIndex(i)}>
              {n.label}
            </Link>
          ) : (
            <a key={n.label} href={n.href} className={pillIndex === i ? 'is-active' : ''} onMouseEnter={() => setHoverIndex(i)} onClick={() => setNavIndex(i)}>
              {n.label}
            </a>
          ),
        )}
      </nav>

      <div className="hero__date" data-rise>
        <span>{day}</span> / {range}
      </div>
      <Link to="/planner" className="btn-black hero__contact" data-rise aria-label="Plan a route">
        <span className="hero__contact-text">Plan Route</span> <span aria-hidden>↗</span>
      </Link>

      <h1 className="hero__title">
        <span className="title-line">
          <span>WEATHER</span>
        </span>
        <span className="title-line">
          <span>
            AWARE<sup>(’26)</sup>
          </span>
        </span>
        <span className="sr-only"> truck routing</span>
      </h1>

      <div className="hero__about" data-rise>
        <div className="eyebrow">● (ABOUT)</div>
        <p>
          Truck routing that reads the forecast at the hour you arrive — not the hour you leave.
        </p>
        <Link to="/planner" className="btn-black">
          Start Planning <span aria-hidden>↗</span>
        </Link>
      </div>

      <div className="stats" data-rise>
        <div className="stats__dark">
          <div className="stats__num">
            {routes}
            <small>options</small>
          </div>
          <div className="stats__label">Routes per trip</div>
          <ul className="marks">
            {MARKS.map((m) => (
              <li key={m.name} title={m.name}>
                <svg viewBox="0 0 20 20" aria-hidden>
                  <path d={m.glyph} />
                </svg>
                <span>{m.name}</span>
              </li>
            ))}
          </ul>
          <Link to="/planner" className="stats__bar">
            Plan a trip <span aria-hidden>↗</span>
          </Link>
        </div>
        <div className="stats__photo">
          <div className="stats__feed">
            <span>Forecast Feed</span>
            <span>00–48</span>
          </div>
          <div className="stats__photo-num">
            {hours}h
            <small>Hourly forecast along the whole corridor</small>
          </div>
        </div>
      </div>

      <div className="growth" data-rise>
        <span className="growth__check" aria-hidden>
          ✓
        </span>
        Risk-first
      </div>

      <div className="available" data-rise>
        Checkpoints every
        <br />
        <span>●</span> 10 · 25 · 50 mi
      </div>

      <Link to="/planner" className="outnow" data-rise>
        <div className="outnow__head">
          <span>Out Now</span>
          <strong>Corridor Heatmap</strong>
          <span className="outnow__year">[0–48h]</span>
        </div>
        <div className="outnow__card">
          <img src="/media/hero-road.jpg" alt="" loading="lazy" />
          <span className="outnow__arrow" aria-hidden>
            ↗
          </span>
          <div className="outnow__progress">
            <i />
          </div>
        </div>
      </Link>

      <div className="plate" data-rise>
        <svg className="plate__mark" viewBox="0 0 30 22" aria-hidden>
          <path d="M1 21 12 1l5 9-6 11z" />
          <path d="M16 21l6-10 7 10z" opacity=".55" />
        </svg>
        <span className="plate__name">WEATHER·AWARE</span>
        <span className="plate__menu" aria-hidden>
          <i />
          <i />
        </span>
      </div>

      <div className="hero__logos" data-rise aria-label="Hazards scored">
        <span>Windline</span>
        <span>·</span>
        <span>Rainfold</span>
        <span>·</span>
        <span>Snowpeak</span>
      </div>
    </header>
  )
}
