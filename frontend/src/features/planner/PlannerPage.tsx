import { Link } from 'react-router-dom'
import { usePlanner } from '../../store/plannerStore'
import { CheckpointTable } from './components/CheckpointTable'
import { ForecastControls } from './components/ForecastControls'
import { MapLegend } from './components/MapLegend'
import { PlanForm } from './components/PlanForm'
import { RouteResults } from './components/RouteResults'
import { MapView } from './map/MapView'
import './planner.css'

export default function PlannerPage() {
  const status = usePlanner((s) => s.status)
  const error = usePlanner((s) => s.error)
  const planTrip = usePlanner((s) => s.planTrip)

  return (
    <div className="planner">
      <aside className="panel">
        <header className="panel__brand">
          <Link to="/" className="brand-mark" aria-label="Weather-Aware home">
            <svg viewBox="0 0 28 20" aria-hidden>
              <path d="M2 18 11 2l4 7-5 9z" />
              <path d="M14 18l5-8 5 8z" opacity=".55" />
            </svg>
            <span>WEATHER·AWARE</span>
          </Link>
          <span className="panel__tag">Truck routing</span>
        </header>

        <div className="panel__intro">
          <h1>Plan the safest haul</h1>
          <p>Three route options, scored against the forecast at the hour your truck reaches every checkpoint.</p>
        </div>

        <PlanForm />

        {status === 'error' && (
          <div className="notice notice--error" role="alert">
            <span>{error}</span>
            <button type="button" className="ghost" onClick={() => void planTrip()}>
              Try again
            </button>
          </div>
        )}
        {status === 'loading' && <ResultsSkeleton />}
        {status === 'ready' && (
          <>
            <RouteResults />
            <CheckpointTable />
          </>
        )}
        {status === 'idle' && (
          <ol className="howto">
            <li><b>01</b> Pick origin &amp; destination, departure and load.</li>
            <li><b>02</b> We fetch three truck routes and sample the forecast every 10/25/50 mi at your ETA.</li>
            <li><b>03</b> Routes are ranked: fewest Severe miles → High miles → average risk → time.</li>
          </ol>
        )}
        <footer className="panel__foot">
          Routing © Valhalla / OSRM · Weather © Open-Meteo · Map © OpenStreetMap, CARTO
        </footer>
      </aside>

      <main className="map-wrap">
        <MapView />
        <MapLegend />
        <ForecastControls />
        {status === 'loading' && (
          <div className="map-loading" role="status">
            <span className="spinner" /> Routing &amp; sampling weather…
          </div>
        )}
      </main>
    </div>
  )
}

function ResultsSkeleton() {
  return (
    <div className="skeleton" aria-hidden>
      <div className="skeleton__block skeleton__block--tall" />
      <div className="skeleton__block" />
      <div className="skeleton__block" />
      <div className="skeleton__block" />
    </div>
  )
}
