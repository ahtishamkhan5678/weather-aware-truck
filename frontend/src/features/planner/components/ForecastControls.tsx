import { useEffect, useMemo } from 'react'
import type { HeatmapLayer } from '../../../api/types'
import { fmt } from '../../../lib/format'
import { HEATMAP_RAMPS, rampGradientCss } from '../../../lib/risk'
import { HEATMAP_MAX_HOUR, selectRoute, usePlanner } from '../../../store/plannerStore'

const LAYERS: HeatmapLayer[] = ['risk', 'wind', 'rain', 'snow']

/** 0–48 h forecast scrubber + layer switcher, floating over the map. */
export function ForecastControls() {
  const heatmap = usePlanner((s) => s.heatmap)
  const status = usePlanner((s) => s.heatmapStatus)
  const error = usePlanner((s) => s.heatmapError)
  const hour = usePlanner((s) => s.hour)
  const layer = usePlanner((s) => s.heatmapLayer)
  const visible = usePlanner((s) => s.heatmapVisible)
  const playing = usePlanner((s) => s.playing)
  const route = usePlanner(selectRoute)
  const { setHour, setLayer, toggleHeatmap, setPlaying } = usePlanner.getState()

  useEffect(() => {
    if (!playing) return
    const t = setInterval(() => {
      const h = usePlanner.getState().hour
      setHour(h >= HEATMAP_MAX_HOUR ? 0 : h + 1)
    }, 420)
    return () => clearInterval(t)
  }, [playing, setHour])

  // Highlight the selected route's trip window on the slider track.
  const tripWindow = useMemo(() => {
    if (!heatmap || !route) return null
    const start = (Date.parse(route.departure) - Date.parse(heatmap.start)) / 3_600_000
    const end = (Date.parse(route.arrival) - Date.parse(heatmap.start)) / 3_600_000
    const a = Math.max(0, Math.min(HEATMAP_MAX_HOUR, start))
    const b = Math.max(0, Math.min(HEATMAP_MAX_HOUR, end))
    return b > a ? { left: (a / HEATMAP_MAX_HOUR) * 100, width: ((b - a) / HEATMAP_MAX_HOUR) * 100 } : null
  }, [heatmap, route])

  if (status === 'idle') return null
  const time = heatmap ? new Date(Date.parse(heatmap.start) + hour * 3_600_000) : null
  const ramp = HEATMAP_RAMPS[layer]

  return (
    <div className="forecast" aria-label="Forecast heatmap controls">
      <div className="forecast__top">
        <div className="segmented segmented--dark" role="radiogroup" aria-label="Heatmap layer">
          {LAYERS.map((l) => (
            <button key={l} type="button" role="radio" aria-checked={layer === l} className={layer === l && visible ? 'is-active' : ''} onClick={() => setLayer(l)}>
              {HEATMAP_RAMPS[l].label.replace(' level', '')}
            </button>
          ))}
        </div>
        <button type="button" className="ghost" onClick={toggleHeatmap} aria-pressed={visible}>
          {visible ? 'Hide' : 'Show'} heatmap
        </button>
      </div>

      {status === 'loading' && (
        <div className="forecast__status">
          <span className="spinner spinner--sm" /> Building 48-hour corridor forecast…
        </div>
      )}
      {status === 'error' && <div className="forecast__status is-error">{error}</div>}

      {heatmap && time && (
        <>
          <div className="forecast__row">
            <button type="button" className="play" onClick={() => setPlaying(!playing)} aria-label={playing ? 'Pause' : 'Play forecast'}>
              {playing ? '❚❚' : '▶'}
            </button>
            <div className="forecast__time">
              <strong>{fmt.dateTime(time)}</strong>
              <span>+{hour} h</span>
            </div>
            <div className="slider">
              {tripWindow && <span className="slider__trip" style={{ left: `${tripWindow.left}%`, width: `${tripWindow.width}%` }} title="Selected route on the road" />}
              <input
                type="range"
                min={0}
                max={HEATMAP_MAX_HOUR}
                step={1}
                value={hour}
                onChange={(e) => setHour(e.target.valueAsNumber)}
                aria-label="Forecast hour"
                aria-valuetext={`${fmt.dateTime(time)}, plus ${hour} hours`}
              />
              <div className="slider__ticks" aria-hidden>
                {[0, 12, 24, 36, 48].map((h) => (
                  <span key={h}>{h}h</span>
                ))}
              </div>
            </div>
          </div>
          <div className="legend">
            <span className="legend__label">
              {ramp.label}
              {ramp.unit && ` (${ramp.unit})`}
            </span>
            <span className="legend__ramp" style={{ background: rampGradientCss(layer) }} />
            <span className="legend__ticks">
              {ramp.ticks.map((t) => (
                <span key={t}>{t}</span>
              ))}
            </span>
          </div>
        </>
      )}
    </div>
  )
}
