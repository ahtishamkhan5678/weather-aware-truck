import { describe, expect, it } from 'vitest'
import { fmt, nextHour, toLocalInput } from './format'
import { rampColor, HEATMAP_RAMPS } from './risk'

describe('format', () => {
  it('formats durations', () => {
    expect(fmt.duration(45 * 60)).toBe('45 min')
    expect(fmt.duration(9 * 3600 + 3 * 60)).toBe('9h 03m')
    expect(fmt.duration(50 * 3600)).toBe('2d 2h 00m')
  })
  it('formats datetime-local input values and next hour', () => {
    const d = new Date(2026, 10, 18, 21, 37)
    expect(toLocalInput(d)).toBe('2026-11-18T21:37')
    const n = nextHour(d)
    expect([n.getHours(), n.getMinutes()]).toEqual([22, 0])
  })
})

describe('risk ramps', () => {
  it('interpolates between stops and clamps at the ends', () => {
    const stops = HEATMAP_RAMPS.wind.stops
    expect(rampColor(stops, -5)[3]).toBe(0)
    expect(rampColor(stops, 999)).toEqual(rampColor(stops, 55))
    const mid = rampColor(stops, 30)[3]
    expect(mid).toBeGreaterThan(rampColor(stops, 25)[3])
    expect(mid).toBeLessThan(rampColor(stops, 35)[3])
  })
})
