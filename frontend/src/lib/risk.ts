import type { HeatmapLayer, RiskKey } from '../api/types'

export const RISK_ORDER: RiskKey[] = ['low', 'moderate', 'high', 'severe', 'no_travel']

export const RISK_META: Record<RiskKey, { label: string; color: string; score: number }> = {
  low: { label: 'Low', color: '#4ade80', score: 0 },
  moderate: { label: 'Moderate', color: '#facc15', score: 1 },
  high: { label: 'High', color: '#fb923c', score: 2 },
  severe: { label: 'Severe', color: '#ef4444', score: 3 },
  no_travel: { label: 'No Travel', color: '#d946ef', score: 4 },
}

export const ROUTE_COLORS: Record<string, string> = { A: '#f4f4f4', B: '#9ca3af', C: '#6b7280' }

/** Colour ramps for the heatmap: [value, r, g, b, alpha 0–1]. Values between stops interpolate. */
type Stop = [number, number, number, number, number]

export const HEATMAP_RAMPS: Record<HeatmapLayer, { stops: Stop[]; unit: string; label: string; ticks: string[] }> = {
  risk: {
    label: 'Risk level',
    unit: '',
    ticks: ['Low', 'Mod', 'High', 'Severe', 'No travel'],
    stops: [
      [0, 74, 222, 128, 0.14],
      [1, 250, 204, 21, 0.5],
      [2, 251, 146, 60, 0.62],
      [3, 239, 68, 68, 0.72],
      [4, 217, 70, 239, 0.82],
    ],
  },
  wind: {
    label: 'Wind',
    unit: 'mph',
    ticks: ['0', '15', '25', '35', '45', '55+'],
    stops: [
      [0, 56, 189, 248, 0],
      [8, 56, 189, 248, 0.12],
      [25, 250, 204, 21, 0.5],
      [35, 251, 146, 60, 0.62],
      [45, 239, 68, 68, 0.72],
      [55, 217, 70, 239, 0.82],
    ],
  },
  rain: {
    label: 'Rain',
    unit: 'in/hr',
    ticks: ['0', '0.10', '0.25', '0.50', '1.00+'],
    stops: [
      [0, 96, 165, 250, 0],
      [0.01, 96, 165, 250, 0.18],
      [0.1, 59, 130, 246, 0.45],
      [0.25, 250, 204, 21, 0.58],
      [0.5, 239, 68, 68, 0.7],
      [1.0, 217, 70, 239, 0.82],
    ],
  },
  snow: {
    label: 'Snow',
    unit: 'in/hr',
    ticks: ['0', '0.5', '1.0', '2.0', '3.0+'],
    stops: [
      [0, 226, 232, 240, 0],
      [0.02, 226, 232, 240, 0.2],
      [0.5, 165, 180, 252, 0.5],
      [1.0, 129, 140, 248, 0.62],
      [2.0, 239, 68, 68, 0.72],
      [3.0, 217, 70, 239, 0.82],
    ],
  },
}

export function rampColor(stops: Stop[], v: number): [number, number, number, number] {
  if (v <= stops[0][0]) return [stops[0][1], stops[0][2], stops[0][3], stops[0][4]]
  for (let i = 1; i < stops.length; i++) {
    const b = stops[i]
    if (v <= b[0]) {
      const a = stops[i - 1]
      const t = (v - a[0]) / (b[0] - a[0])
      return [a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t, a[3] + (b[3] - a[3]) * t, a[4] + (b[4] - a[4]) * t]
    }
  }
  const z = stops[stops.length - 1]
  return [z[1], z[2], z[3], z[4]]
}

export function rampGradientCss(layer: HeatmapLayer): string {
  const { stops } = HEATMAP_RAMPS[layer]
  const lo = stops[0][0]
  const hi = stops[stops.length - 1][0]
  const parts = stops.map(([v, r, g, b, a]) => {
    const pct = ((v - lo) / (hi - lo)) * 100
    return `rgba(${r},${g},${b},${Math.max(a, 0.25)}) ${pct.toFixed(1)}%`
  })
  return `linear-gradient(90deg, ${parts.join(', ')})`
}
