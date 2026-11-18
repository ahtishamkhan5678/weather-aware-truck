import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../../api/client'
import type { RulesResponse } from '../../api/types'
import { RISK_META } from '../../lib/risk'
import { isRecording, useCountUp, useInView } from './hooks'

const ICONS = [
  'M3 8h10a3 3 0 1 0-3-3M3 13h13a3 3 0 1 1-3 3', // wind
  'M12 3c4 5 6 8 6 11a6 6 0 0 1-12 0c0-3 2-6 6-11z', // rain
  'M12 2v20M4 7l16 10M20 7 4 17', // snow
  'M3 15V8h11v7M14 11h4l3 3v1h-7M6 18a2 2 0 1 0 0-.1M17 18a2 2 0 1 0 0-.1', // truck
  'M12 6v6l4 2M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z', // clock
  'M12 21s-7-6-7-12a7 7 0 0 1 14 0c0 6-7 12-7 12zM12 11a2 2 0 1 0 0-4 2 2 0 0 0 0 4z', // pin
  'M12 3 4 6v6c0 5 4 8 8 9 4-1 8-4 8-9V6z', // shield
  'M4 19h16M6 15l4-6 4 3 4-7', // trend
]

/** "Trusted by" panel → the rules the app is built on (served live from /api/rules). */
export function RulesPanel() {
  const [ref, inView] = useInView<HTMLDivElement>(0.25)
  const [recStart, setRecStart] = useState(false)
  const start = inView || recStart
  const frames = useCountUp(49, start, 1700, isRecording() ? 0 : 0)
  const levels = useCountUp(5, start, 1700)
  const [rules, setRules] = useState<RulesResponse | null>(null)
  const [rulesError, setRulesError] = useState(false)

  useEffect(() => {
    if (!isRecording()) return
    const t = setTimeout(() => setRecStart(true), 3500)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    api.rules().then(setRules, () => setRulesError(true))
  }, [])

  return (
    <section className="trust" id="rules">
      <div className={`trust__panel${start ? ' is-in' : ''}`} ref={ref}>
        <div className="trust__left">
          <h2 className="trust__title">
            <span>Built on</span>
            <span>Clear</span>
            <span>Risk</span>
            <span>Rules</span>
          </h2>
          <span className="glass glass--a" aria-hidden>
            ✳
          </span>
          <span className="glass glass--b" aria-hidden>
            <i />
            <i />
            <i />
            <i />
          </span>
          <p className="trust__copy">
            Wind, rain and snow are scored at every checkpoint, at the hour the truck gets there. Heavy loads
            escalate high winds. Routes are ranked by Severe miles first — then High miles, average risk and
            time.
          </p>
        </div>

        <div className="trust__cards">
          <article className="tcard tcard--light">
            <ul className="avatars">
              {ICONS.map((d, i) => (
                <li key={i} style={{ transitionDelay: `${i * 70}ms` }}>
                  <svg viewBox="0 0 24 24" aria-hidden>
                    <path d={d} />
                  </svg>
                </li>
              ))}
            </ul>
            <div className="tcard__num">{frames}</div>
            <div className="tcard__label">Hourly forecast frames</div>
          </article>

          <article className="tcard tcard--dark">
            <div className="tcard__num">{levels}</div>
            <div className="tcard__label">Risk levels</div>
            <svg className="laurel" viewBox="0 0 200 120" aria-label="Safest route first 2026">
              <g fill="none" stroke="#f4f4f4" strokeWidth="2" strokeLinecap="round">
                {Array.from({ length: 6 }).map((_, i) => (
                  <g key={i}>
                    <ellipse cx={42 - i * 2} cy={92 - i * 13} rx="10" ry="4.5" transform={`rotate(${-50 + i * 12} ${42 - i * 2} ${92 - i * 13})`} />
                    <ellipse cx={158 + i * 2} cy={92 - i * 13} rx="10" ry="4.5" transform={`rotate(${50 - i * 12} ${158 + i * 2} ${92 - i * 13})`} />
                  </g>
                ))}
              </g>
              <text x="100" y="50" textAnchor="middle" fill="#f4f4f4" fontSize="12" fontWeight="700" letterSpacing="1.5">SAFEST</text>
              <text x="100" y="66" textAnchor="middle" fill="#f4f4f4" fontSize="12" fontWeight="700" letterSpacing="1.5">ROUTE FIRST</text>
              <text x="100" y="86" textAnchor="middle" fill="#8a8a8a" fontSize="11">2026</text>
            </svg>
            <p className="tcard__note">
              Low → Moderate → High → Severe → No Travel.
              <br />
              The worst hazard sets the level.
            </p>
          </article>

          <article className="tcard tcard--portrait" aria-hidden>
            <img src="/media/hero-road.jpg" alt="" loading="lazy" />
          </article>
        </div>
      </div>

      <div className="matrix">
        <div className="matrix__head">
          <h3>Risk matrix</h3>
          <span>Served live by the API — the same rules the planner uses.</span>
        </div>
        {rulesError && <p className="matrix__error">Rules are unavailable right now.</p>}
        {rules && <RulesTable rules={rules} />}
        <Link to="/planner" className="btn-white">
          Open the planner <span aria-hidden>↗</span>
        </Link>
      </div>
    </section>
  )
}

function RulesTable({ rules }: { rules: RulesResponse }) {
  const levels = rules.levels.map((l) => l.key)
  const cell = (h: RulesResponse['hazards'][number], key: string) => {
    const idx = h.thresholds.findIndex((t) => t.level === key)
    if (key === 'low') return `< ${h.thresholds[0].minimum}`
    const t = h.thresholds[idx]
    const next = h.thresholds[idx + 1]
    if (!next) return `${t.inclusive ? '≥' : '>'} ${t.minimum}`
    // Whole-mph wind reads like the brief (25–34); rates show the shared boundary.
    return h.unit === 'mph' ? `${t.minimum} – ${next.minimum - 1}` : `${t.minimum} – ${next.minimum}`
  }
  return (
    <>
      <div className="matrix__scroll">
        <table className="rules-table">
          <thead>
            <tr>
              <th scope="col">Condition</th>
              {levels.map((k) => (
                <th key={k} scope="col">
                  <i className="dot" style={{ background: RISK_META[k].color }} />
                  {RISK_META[k].label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rules.hazards.map((h) => (
              <tr key={h.hazard}>
                <th scope="row">
                  {h.hazard[0].toUpperCase() + h.hazard.slice(1)} <small>{h.unit}</small>
                </th>
                {levels.map((k) => (
                  <td key={k}>{cell(h, k)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="load-rules">
        {rules.load_rules.map((r) => (
          <li key={r.description}>
            <i className="dot" style={{ background: RISK_META[r.result].color }} />
            {r.description} → <strong>{RISK_META[r.result].label}</strong>
          </li>
        ))}
      </ul>
    </>
  )
}
