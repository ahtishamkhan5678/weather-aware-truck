import { useEffect, useRef } from 'react'
import { fmt } from '../../../lib/format'
import { RISK_META } from '../../../lib/risk'
import { selectRoute, usePlanner } from '../../../store/plannerStore'

export function CheckpointTable() {
  const route = usePlanner(selectRoute)
  const focused = usePlanner((s) => s.focusedCheckpoint)
  const focus = usePlanner((s) => s.focusCheckpoint)
  const listRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!focused) return
    listRef.current?.querySelector(`[data-index="${focused.index}"]`)?.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
  }, [focused])

  if (!route) return null
  return (
    <section className="checkpoints" aria-label={`Checkpoints for route ${route.id}`}>
      <header className="section-head">
        <h3>
          Route {route.id} · {route.checkpoints.length} checkpoints
        </h3>
        <span>Weather at truck ETA</span>
      </header>
      <div className="timeline" aria-hidden>
        {route.checkpoints.map((cp) => (
          <button
            key={cp.index}
            tabIndex={-1}
            style={{ flexGrow: cp.represented_mi, background: RISK_META[cp.level].color }}
            className={focused?.index === cp.index && focused.routeId === route.id ? 'is-focused' : ''}
            onClick={() => focus(route.id, cp.index)}
            title={`Mile ${cp.distance_mi.toFixed(0)} · ${RISK_META[cp.level].label}`}
          />
        ))}
      </div>
      <div className="cp-table" ref={listRef} role="table">
        <div className="cp-row cp-row--head" role="row">
          <span role="columnheader">Mile</span>
          <span role="columnheader">ETA</span>
          <span role="columnheader">Wind</span>
          <span role="columnheader">Rain</span>
          <span role="columnheader">Snow</span>
          <span role="columnheader">Risk</span>
        </div>
        {route.checkpoints.map((cp) => {
          const meta = RISK_META[cp.level]
          const isFocused = focused?.routeId === route.id && focused.index === cp.index
          return (
            <button
              key={cp.index}
              type="button"
              role="row"
              data-index={cp.index}
              className={`cp-row${isFocused ? ' is-focused' : ''}`}
              onClick={() => focus(route.id, cp.index)}
            >
              <span role="cell">{cp.distance_mi.toFixed(0)}</span>
              <span role="cell">{fmt.dateTime(cp.eta)}</span>
              <span role="cell" className={cp.drivers.includes('wind') ? 'is-driver' : ''}>
                {cp.weather.wind_mph.toFixed(1)}
              </span>
              <span role="cell" className={cp.drivers.includes('rain') ? 'is-driver' : ''}>
                {cp.weather.rain_in_hr.toFixed(2)}
              </span>
              <span role="cell" className={cp.drivers.includes('snow') ? 'is-driver' : ''}>
                {cp.weather.snow_in_hr.toFixed(2)}
              </span>
              <span role="cell">
                <i className="dot" style={{ background: meta.color }} />
                {meta.label}
              </span>
            </button>
          )
        })}
      </div>
      <p className="cp-foot">Units: wind mph · rain &amp; snow in/hr. Highlighted values drive the level.</p>
    </section>
  )
}
