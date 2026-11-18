import { RISK_META, RISK_ORDER } from '../../../lib/risk'

export function MapLegend() {
  return (
    <div className="map-legend" aria-label="Checkpoint risk legend">
      {RISK_ORDER.map((k) => (
        <span key={k}>
          <i className="dot" style={{ background: RISK_META[k].color }} />
          {RISK_META[k].label}
        </span>
      ))}
    </div>
  )
}
