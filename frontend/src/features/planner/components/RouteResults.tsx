import type { RouteDTO } from '../../../api/types'
import { fmt } from '../../../lib/format'
import { RISK_META } from '../../../lib/risk'
import { usePlanner } from '../../../store/plannerStore'
import { RiskBar } from './RiskBar'

const CRITERIA: Record<string, string> = {
  no_travel_miles: 'fewest No-Travel miles',
  severe_miles: 'fewest Severe miles',
  high_miles: 'fewest High miles',
  average_risk: 'lowest average risk',
  travel_time: 'shortest travel time (risk tied)',
}

export function RouteResults() {
  const plan = usePlanner((s) => s.plan)
  const selected = usePlanner((s) => s.selectedRouteId)
  const select = usePlanner((s) => s.selectRoute)
  if (!plan) return null
  const best = plan.routes.find((r) => r.id === plan.recommendation.route_id)!
  const ordered = plan.recommendation.order.map((id) => plan.routes.find((r) => r.id === id)!)

  return (
    <section className="results" aria-label="Route options">
      <div className={`recommendation${plan.recommendation.all_routes_blocked ? ' is-blocked' : ''}`}>
        <div className="recommendation__eyebrow">● Recommended</div>
        <div className="recommendation__title">
          Route {best.id}
          <span>{best.roads.slice(0, 2).join(' · ') || 'Fastest safe corridor'}</span>
        </div>
        <p className="recommendation__why">
          Chosen for <strong>{CRITERIA[plan.recommendation.decided_by] ?? plan.recommendation.decided_by}</strong>.
        </p>
        <ul className="recommendation__reasons">
          {plan.recommendation.reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      </div>

      {plan.warnings.map((w) => (
        <div key={w} className="notice notice--warn" role="status">
          {w}
        </div>
      ))}

      <div className="route-cards">
        {ordered.map((r) => (
          <RouteCard key={r.id} route={r} selected={r.id === selected} onSelect={() => select(r.id)} />
        ))}
      </div>
    </section>
  )
}

function RouteCard({ route: r, selected, onSelect }: { route: RouteDTO; selected: boolean; onSelect: () => void }) {
  const m = r.risk.miles_by_level
  const worst = RISK_META[r.risk.max_level]
  return (
    <button type="button" className={`route-card${selected ? ' is-selected' : ''}`} onClick={onSelect} aria-pressed={selected}>
      <div className="route-card__head">
        <span className="route-card__id">{r.id}</span>
        <div className="route-card__name">
          <strong>{r.roads.slice(0, 3).join(' · ') || `Route ${r.id}`}</strong>
          <small>
            #{r.rank} of 3 · via {r.provider === 'valhalla' ? 'truck routing' : 'road routing'}
          </small>
        </div>
        {r.recommended && <span className="badge">Best</span>}
      </div>
      <dl className="route-card__stats">
        <div>
          <dt>Distance</dt>
          <dd>{fmt.miles(r.distance_mi)}</dd>
        </div>
        <div>
          <dt>Trip time</dt>
          <dd>{fmt.duration(r.trip_s)}</dd>
        </div>
        <div>
          <dt>Arrive</dt>
          <dd>{fmt.dateTime(r.arrival)}</dd>
        </div>
      </dl>
      <RiskBar miles={m} total={r.distance_mi} />
      <dl className="route-card__risk">
        <div>
          <dt>Severe+</dt>
          <dd>{fmt.milesPrecise(m.severe + m.no_travel)}</dd>
        </div>
        <div>
          <dt>High</dt>
          <dd>{fmt.milesPrecise(m.high)}</dd>
        </div>
        <div>
          <dt>Avg risk</dt>
          <dd>{r.risk.average.toFixed(2)}</dd>
        </div>
        <div>
          <dt>Worst</dt>
          <dd>
            <i className="dot" style={{ background: worst.color }} /> {worst.label}
          </dd>
        </div>
      </dl>
      {r.rest_stops.length > 0 && (
        <p className="route-card__hos">
          Includes {r.rest_stops.filter((s) => s.kind === 'break').length} × 30-min break
          {r.rest_stops.some((s) => s.kind === 'rest') && `, ${r.rest_stops.filter((s) => s.kind === 'rest').length} × 10-h rest`} (HOS) ·
          driving {fmt.duration(r.driving_s)}
        </p>
      )}
    </button>
  )
}
