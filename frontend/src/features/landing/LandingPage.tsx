import { Hero } from './Hero'
import { RulesPanel } from './RulesPanel'
import { Statement } from './Statement'
import { Topbar } from './Topbar'
import './landing.css'

export default function LandingPage() {
  return (
    <div className="landing">
      <Topbar />
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
