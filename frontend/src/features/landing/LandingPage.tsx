import { Hero } from './Hero'
import { RulesPanel } from './RulesPanel'
import { Statement } from './Statement'
import './landing.css'

export default function LandingPage() {
  return (
    <div className="landing">
      <Hero />
      <div className="bar">
        <span>
          EST <em>2026</em>
        </span>
        <a href="#method" className="bar__scroll">
          SCROLL DOWN
          <span className="bar__arrow" aria-hidden>
            ↓
          </span>
        </a>
        <span className="bar__grey">RISK IN DETAILS</span>
      </div>
      <Statement />
      <RulesPanel />
      <footer className="footer">
        <span>Weather-Aware Truck Routing</span>
        <span>
          Photo: Zoshua Colah / Unsplash · Routing: Valhalla, OSRM · Weather: Open-Meteo · Maps: © OpenStreetMap, CARTO
        </span>
      </footer>
    </div>
  )
}
