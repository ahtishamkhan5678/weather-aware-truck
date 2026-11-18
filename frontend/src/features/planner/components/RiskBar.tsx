import type { RiskKey } from '../../../api/types'
import { RISK_META, RISK_ORDER } from '../../../lib/risk'

/** Stacked bar of miles per risk level. */
export function RiskBar({ miles, total }: { miles: Record<RiskKey, number>; total: number }) {
  return (
    <div className="risk-bar" role="img" aria-label={RISK_ORDER.map((k) => `${RISK_META[k].label} ${Math.round(miles[k])} mi`).join(', ')}>
      {RISK_ORDER.map((k) =>
        miles[k] > 0 ? (
          <span key={k} style={{ flexGrow: miles[k] / (total || 1), background: RISK_META[k].color }} title={`${RISK_META[k].label}: ${miles[k].toFixed(1)} mi`} />
        ) : null,
      )}
    </div>
  )
}
