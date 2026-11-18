import type { CheckpointDTO, RiskKey } from '../api/types'

export type LonLat = [number, number]

const R = 6371008.8
const toRad = (d: number) => (d * Math.PI) / 180

export function haversineMi(a: LonLat, b: LonLat): number {
  const dLat = toRad(b[1] - a[1])
  const dLon = toRad(b[0] - a[0])
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(toRad(a[1])) * Math.cos(toRad(b[1])) * Math.sin(dLon / 2) ** 2
  return (2 * R * Math.asin(Math.min(1, Math.sqrt(h)))) / 1609.344
}

export function mercatorY(lat: number): number {
  const s = Math.sin(toRad(Math.max(-85, Math.min(85, lat))))
  return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI)
}

export function latFromMercatorY(y: number): number {
  const n = Math.PI - 2 * Math.PI * y
  return (180 / Math.PI) * Math.atan(0.5 * (Math.exp(n) - Math.exp(-n)))
}

export function bounds(lines: LonLat[][]): [LonLat, LonLat] {
  let w = Infinity, s = Infinity, e = -Infinity, n = -Infinity
  for (const line of lines)
    for (const [x, y] of line) {
      if (x < w) w = x
      if (x > e) e = x
      if (y < s) s = y
      if (y > n) n = y
    }
  return [[w, s], [e, n]]
}

/** Point at a fraction (0–1) of a polyline's length — used to place route labels. */
export function pointAlong(line: LonLat[], fraction: number): LonLat {
  const cum = [0]
  for (let i = 1; i < line.length; i++) cum.push(cum[i - 1] + haversineMi(line[i - 1], line[i]))
  const target = cum[cum.length - 1] * fraction
  for (let i = 1; i < line.length; i++) {
    if (cum[i] >= target) {
      const t = (target - cum[i - 1]) / (cum[i] - cum[i - 1] || 1)
      return [line[i - 1][0] + (line[i][0] - line[i - 1][0]) * t, line[i - 1][1] + (line[i][1] - line[i - 1][1]) * t]
    }
  }
  return line[line.length - 1]
}

/**
 * Split a route into pieces coloured by the checkpoint that represents each stretch
 * (half-way to neighbouring checkpoints — the same rule the backend uses for mile totals).
 */
export function riskSegments(
  line: LonLat[],
  checkpoints: CheckpointDTO[],
  totalMi: number,
): { level: RiskKey; coords: LonLat[] }[] {
  if (line.length < 2 || checkpoints.length === 0) return []
  const cum = [0]
  for (let i = 1; i < line.length; i++) cum.push(cum[i - 1] + haversineMi(line[i - 1], line[i]))
  const scale = totalMi / (cum[cum.length - 1] || 1) // geometry is simplified; align to route miles
  const at = (mi: number): LonLat => {
    const d = mi / scale
    for (let i = 1; i < line.length; i++)
      if (cum[i] >= d) {
        const t = (d - cum[i - 1]) / (cum[i] - cum[i - 1] || 1)
        return [line[i - 1][0] + (line[i][0] - line[i - 1][0]) * t, line[i - 1][1] + (line[i][1] - line[i - 1][1]) * t]
      }
    return line[line.length - 1]
  }
  const out: { level: RiskKey; coords: LonLat[] }[] = []
  checkpoints.forEach((cp, i) => {
    const lo = i === 0 ? 0 : (checkpoints[i - 1].distance_mi + cp.distance_mi) / 2
    const hi = i === checkpoints.length - 1 ? totalMi : (cp.distance_mi + checkpoints[i + 1].distance_mi) / 2
    if (hi <= lo) return
    const coords: LonLat[] = [at(lo)]
    for (let k = 0; k < line.length; k++) {
      const mi = cum[k] * scale
      if (mi > lo && mi < hi) coords.push(line[k])
    }
    coords.push(at(hi))
    const prev = out[out.length - 1]
    if (prev && prev.level === cp.level) prev.coords.push(...coords.slice(1))
    else out.push({ level: cp.level, coords })
  })
  return out
}
