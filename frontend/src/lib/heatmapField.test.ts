import { describe, expect, it } from 'vitest'
import type { HeatmapResponse } from '../api/types'
import { HeatmapField } from './heatmapField'
import { riskSegments } from './geo'

function grid(values: (number | null)[], hours = 1): HeatmapResponse {
  // 2 × 2 grid, step 1°, at 30–31 N, 100–99 W.
  const active = values.map((v, i) => (v === null ? -1 : i)).filter((i) => i >= 0)
  const layer = active.flatMap((i) => Array(hours).fill(values[i]))
  return {
    start: '2026-11-18T00:00:00Z',
    hours,
    grid: { south: 30, west: -100, step: 1, rows: 2, cols: 2 },
    active,
    layers: { risk: layer, wind: layer, rain: layer, snow: layer },
  }
}

describe('HeatmapField', () => {
  it('bilinearly interpolates values between nodes', () => {
    const f = new HeatmapField(grid([0, 40, 0, 40]), 64)
    const mid = f.valueAtPixel('wind', 0, Math.floor(f.width / 2), Math.floor(f.height / 2))
    expect(mid).toBeGreaterThan(15)
    expect(mid).toBeLessThan(25)
    expect(f.valueAtPixel('wind', 0, 0, 0)).toBeLessThan(2)
  })

  it('ignores nodes outside the corridor instead of treating them as zero', () => {
    const f = new HeatmapField(grid([30, null, 30, null]), 64)
    expect(f.valueAtPixel('wind', 0, Math.floor(f.width / 2), 5)).toBeCloseTo(30, 5)
  })

  it('keeps transparent pixels where no data exists', () => {
    const f = new HeatmapField(grid([null, null, null, 2]), 64)
    const px = f.pixels('risk', 0)
    expect(px[3]).toBe(0) // top-left pixel is far from the only active node
  })
})

describe('riskSegments', () => {
  it('colours stretches by checkpoint and merges equal neighbours', () => {
    const line: [number, number][] = [[-100, 30], [-99, 30], [-98, 30]]
    const cp = (d: number, level: 'low' | 'severe') => ({ distance_mi: d, level }) as never
    const segs = riskSegments(line, [cp(0, 'low'), cp(60, 'low'), cp(120, 'severe')], 120)
    expect(segs.map((s) => s.level)).toEqual(['low', 'severe'])
  })
})
