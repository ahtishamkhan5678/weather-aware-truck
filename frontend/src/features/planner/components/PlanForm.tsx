import { useState, type FormEvent } from 'react'
import type { Interval } from '../../../api/types'
import { toLocalInput } from '../../../lib/format'
import { usePlanner } from '../../../store/plannerStore'
import { PlaceInput } from './PlaceInput'

const INTERVALS: Interval[] = [10, 25, 50]
const PRESETS = [
  { label: 'Denver → Salt Lake City', o: { label: 'Denver, Colorado, US', lat: 39.7392, lon: -104.9903 }, d: { label: 'Salt Lake City, Utah, US', lat: 40.7608, lon: -111.891 } },
  { label: 'Chicago → Minneapolis', o: { label: 'Chicago, Illinois, US', lat: 41.8781, lon: -87.6298 }, d: { label: 'Minneapolis, Minnesota, US', lat: 44.9778, lon: -93.265 } },
  { label: 'Dallas → Albuquerque', o: { label: 'Dallas, Texas, US', lat: 32.7767, lon: -96.797 }, d: { label: 'Albuquerque, New Mexico, US', lat: 35.0844, lon: -106.6504 } },
]

export function PlanForm() {
  const form = usePlanner((s) => s.form)
  const status = usePlanner((s) => s.status)
  const setForm = usePlanner((s) => s.setForm)
  const swap = usePlanner((s) => s.swapPlaces)
  const planTrip = usePlanner((s) => s.planTrip)

  // Bounds for the date picker, fixed at mount (pure render).
  const [{ now, max }] = useState(() => {
    const n = new Date()
    return { now: n, max: new Date(n.getTime() + 10 * 86_400_000) }
  })
  const canSubmit =
    form.origin.text.trim().length >= 2 && form.destination.text.trim().length >= 2 && form.loadLb >= 0 && status !== 'loading'

  const submit = (e: FormEvent) => {
    e.preventDefault()
    if (canSubmit) void planTrip()
  }

  return (
    <form className="plan-form" onSubmit={submit} aria-label="Plan a trip">
      <div className="plan-form__places">
        <PlaceInput label="Origin" marker="origin" placeholder="City, address or depot" value={form.origin} onChange={(origin) => setForm({ origin })} />
        <button type="button" className="swap" onClick={swap} aria-label="Swap origin and destination" title="Swap">
          ⇅
        </button>
        <PlaceInput label="Destination" marker="destination" placeholder="Where is the load going?" value={form.destination} onChange={(destination) => setForm({ destination })} />
      </div>

      <div className="plan-form__row">
        <div className="field">
          <label htmlFor="departure">Departure</label>
          <input
            id="departure"
            type="datetime-local"
            value={form.departureLocal}
            min={toLocalInput(now)}
            max={toLocalInput(max)}
            onChange={(e) => setForm({ departureLocal: e.target.value })}
            required
          />
        </div>
        <div className="field">
          <label htmlFor="load">Load weight (lb)</label>
          <input
            id="load"
            type="number"
            inputMode="numeric"
            min={0}
            max={100000}
            step={500}
            value={Number.isFinite(form.loadLb) ? form.loadLb : ''}
            onChange={(e) => setForm({ loadLb: e.target.valueAsNumber })}
            required
          />
        </div>
      </div>

      <div className="field">
        <span className="field__label" id="interval-label">Weather checkpoint every</span>
        <div className="segmented" role="radiogroup" aria-labelledby="interval-label">
          {INTERVALS.map((i) => (
            <button
              key={i}
              type="button"
              role="radio"
              aria-checked={form.interval === i}
              className={form.interval === i ? 'is-active' : ''}
              onClick={() => setForm({ interval: i })}
            >
              {i} mi
            </button>
          ))}
        </div>
      </div>

      <button type="submit" className="btn btn--primary btn--block" disabled={!canSubmit}>
        {status === 'loading' ? (
          <>
            <span className="spinner" aria-hidden /> Scoring routes against the forecast…
          </>
        ) : (
          <>Find the safest route ↗</>
        )}
      </button>

      <div className="presets" aria-label="Example trips">
        {PRESETS.map((p) => (
          <button
            key={p.label}
            type="button"
            onClick={() => setForm({ origin: { text: p.o.label, place: p.o }, destination: { text: p.d.label, place: p.d } })}
          >
            {p.label}
          </button>
        ))}
      </div>
    </form>
  )
}
