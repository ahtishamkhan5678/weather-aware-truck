/**
 * Turns the backend's sparse corridor grid into smooth heatmap frames.
 *
 * - Values (not colours) are bilinearly interpolated, so a 45 mph cell next to a 25 mph
 *   cell really shows ~35 mph in between.
 * - Canvas rows are spaced in Web-Mercator Y, matching how MapLibre stretches an image
 *   source between its corner coordinates (no north/south drift on long trips).
 * - Inactive grid nodes (outside the corridor) are skipped and the remaining weights
 *   renormalised; a soft mask drawn from the routes clips the field to the corridor.
 * - Frames are rendered lazily and memoised, so scrubbing the slider is O(1) after the
 *   first visit of an hour.
 */
import type { HeatmapLayer, HeatmapResponse } from '../api/types'
import { latFromMercatorY, mercatorY, type LonLat } from './geo'
import { HEATMAP_RAMPS, rampColor } from './risk'

export interface FieldBounds {
  west: number
  south: number
  east: number
  north: number
}

export class HeatmapField {
  readonly bounds: FieldBounds
  readonly hours: number
  readonly width: number
  readonly height: number
  private readonly grids: Record<HeatmapLayer, Float32Array>
  private readonly rows: number
  private readonly cols: number
  private readonly step: number
  // Per-pixel sampling plan, computed once and reused by every frame.
  private readonly sampleIdx: Int32Array
  private readonly sampleW: Float32Array

  constructor(data: HeatmapResponse, maxSize = 360) {
    const { south, west, step, rows, cols } = data.grid
    this.rows = rows
    this.cols = cols
    this.step = step
    this.hours = data.hours
    this.bounds = { west, south, east: west + (cols - 1) * step, north: south + (rows - 1) * step }

    const nodes = rows * cols
    this.grids = {} as Record<HeatmapLayer, Float32Array>
    for (const layer of Object.keys(data.layers) as HeatmapLayer[]) {
      const grid = new Float32Array(nodes * this.hours).fill(Number.NaN)
      const values = data.layers[layer]
      data.active.forEach((node, k) => {
        grid.set(values.slice(k * this.hours, (k + 1) * this.hours), node * this.hours)
      })
      this.grids[layer] = grid
    }

    // Canvas size follows the on-map aspect ratio (Mercator).
    const yN = mercatorY(this.bounds.north)
    const yS = mercatorY(this.bounds.south)
    const xSpan = (this.bounds.east - this.bounds.west) / 360
    const ySpan = yS - yN
    const aspect = xSpan / ySpan
    this.width = Math.max(32, Math.round(aspect >= 1 ? maxSize : maxSize * aspect))
    this.height = Math.max(32, Math.round(aspect >= 1 ? maxSize / aspect : maxSize))

    const px = this.width * this.height
    this.sampleIdx = new Int32Array(px * 4)
    this.sampleW = new Float32Array(px * 4)
    for (let y = 0; y < this.height; y++) {
      const lat = latFromMercatorY(yN + ((y + 0.5) / this.height) * ySpan)
      const gr = Math.min(Math.max((lat - south) / step, 0), rows - 1.0001)
      const r0 = Math.floor(gr)
      const fy = gr - r0
      for (let x = 0; x < this.width; x++) {
        const lon = this.bounds.west + ((x + 0.5) / this.width) * (this.bounds.east - this.bounds.west)
        const gc = Math.min(Math.max((lon - west) / step, 0), cols - 1.0001)
        const c0 = Math.floor(gc)
        const fx = gc - c0
        const p = (y * this.width + x) * 4
        this.sampleIdx[p] = r0 * cols + c0
        this.sampleIdx[p + 1] = r0 * cols + c0 + 1
        this.sampleIdx[p + 2] = (r0 + 1) * cols + c0
        this.sampleIdx[p + 3] = (r0 + 1) * cols + c0 + 1
        this.sampleW[p] = (1 - fx) * (1 - fy)
        this.sampleW[p + 1] = fx * (1 - fy)
        this.sampleW[p + 2] = (1 - fx) * fy
        this.sampleW[p + 3] = fx * fy
      }
    }
  }

  /** Interpolated value at pixel (x, y) for an hour; NaN when outside the corridor grid. */
  valueAtPixel(layer: HeatmapLayer, hour: number, x: number, y: number): number {
    const grid = this.grids[layer]
    const p = (y * this.width + x) * 4
    let sum = 0
    let wsum = 0
    for (let k = 0; k < 4; k++) {
      const v = grid[this.sampleIdx[p + k] * this.hours + hour]
      const w = this.sampleW[p + k]
      if (!Number.isNaN(v) && w > 0) {
        sum += v * w
        wsum += w
      }
    }
    return wsum > 0.05 ? sum / wsum : Number.NaN
  }

  /** Raw node value (used by tests and tooltips). */
  nodeValue(layer: HeatmapLayer, row: number, col: number, hour: number): number {
    return this.grids[layer][(row * this.cols + col) * this.hours + hour]
  }

  /** RGBA pixels for one frame. */
  pixels(layer: HeatmapLayer, hour: number): Uint8ClampedArray {
    const { stops } = HEATMAP_RAMPS[layer]
    const out = new Uint8ClampedArray(this.width * this.height * 4)
    for (let y = 0; y < this.height; y++)
      for (let x = 0; x < this.width; x++) {
        const v = this.valueAtPixel(layer, hour, x, y)
        if (Number.isNaN(v)) continue
        const [r, g, b, a] = rampColor(stops, v)
        const i = (y * this.width + x) * 4
        out[i] = r
        out[i + 1] = g
        out[i + 2] = b
        out[i + 3] = a * 255
      }
    return out
  }

  /** Lon/lat → canvas pixel (for drawing the corridor mask). */
  project([lon, lat]: LonLat): [number, number] {
    const yN = mercatorY(this.bounds.north)
    const yS = mercatorY(this.bounds.south)
    return [
      ((lon - this.bounds.west) / (this.bounds.east - this.bounds.west)) * this.width,
      ((mercatorY(lat) - yN) / (yS - yN)) * this.height,
    ]
  }

  /** MapLibre image-source corners: top-left, top-right, bottom-right, bottom-left. */
  get corners(): [LonLat, LonLat, LonLat, LonLat] {
    const { west, south, east, north } = this.bounds
    return [[west, north], [east, north], [east, south], [west, south]]
  }

  get cellSizeDeg(): number {
    return this.step
  }

  get gridRows(): number {
    return this.rows
  }
}

/** Browser-only: renders + caches frames as object URLs (PNG) for MapLibre's image source. */
export class HeatmapFrameCache {
  private readonly cache = new Map<string, string>()
  private readonly canvas: HTMLCanvasElement
  private readonly mask: HTMLCanvasElement
  private readonly field: HeatmapField

  constructor(field: HeatmapField, routes: LonLat[][], corridorMi = 30) {
    this.field = field
    this.canvas = document.createElement('canvas')
    this.canvas.width = field.width
    this.canvas.height = field.height
    this.mask = document.createElement('canvas')
    this.mask.width = field.width
    this.mask.height = field.height
    const ctx = this.mask.getContext('2d')!
    // Corridor width in pixels (degrees of latitude → pixels at the grid's mid latitude).
    const midLat = (field.bounds.north + field.bounds.south) / 2
    const [, y0] = field.project([field.bounds.west, midLat])
    const [, y1] = field.project([field.bounds.west, midLat + corridorMi / 69])
    const widthPx = Math.max(6, Math.abs(y1 - y0) * 2)
    ctx.filter = `blur(${Math.max(2, widthPx / 5)}px)`
    ctx.strokeStyle = '#fff'
    ctx.lineCap = 'round'
    ctx.lineJoin = 'round'
    ctx.lineWidth = widthPx
    for (const line of routes) {
      ctx.beginPath()
      line.forEach((p, i) => {
        const [x, y] = field.project(p)
        if (i === 0) ctx.moveTo(x, y)
        else ctx.lineTo(x, y)
      })
      ctx.stroke()
    }
  }

  frame(layer: HeatmapLayer, hour: number): string {
    const key = `${layer}:${hour}`
    const hit = this.cache.get(key)
    if (hit) return hit
    const ctx = this.canvas.getContext('2d')!
    ctx.globalCompositeOperation = 'source-over'
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height)
    const img = new ImageData(this.field.pixels(layer, hour) as Uint8ClampedArray<ArrayBuffer>, this.field.width, this.field.height)
    ctx.putImageData(img, 0, 0)
    ctx.globalCompositeOperation = 'destination-in'
    ctx.drawImage(this.mask, 0, 0)
    const url = this.canvas.toDataURL('image/png')
    this.cache.set(key, url)
    return url
  }

  /** Render upcoming frames when the browser is idle so playback never stutters. */
  prefetch(layer: HeatmapLayer, from: number): void {
    const ric: (cb: () => void) => void =
      'requestIdleCallback' in window ? (cb) => window.requestIdleCallback(cb) : (cb) => setTimeout(cb, 16)
    let h = from
    const step = () => {
      if (h >= this.field.hours) return
      this.frame(layer, h++)
      ric(step)
    }
    ric(step)
  }
}
