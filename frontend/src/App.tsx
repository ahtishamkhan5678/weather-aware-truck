import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import LandingPage from './features/landing/LandingPage'

// The planner pulls in MapLibre (~1 MB); load it only when needed.
const PlannerPage = lazy(() => import('./features/planner/PlannerPage'))

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<LandingPage />} />
        <Route
          path="/planner"
          element={
            <Suspense fallback={<div className="route-fallback">Loading planner…</div>}>
              <PlannerPage />
            </Suspense>
          }
        />
        <Route path="*" element={<LandingPage />} />
      </Routes>
    </BrowserRouter>
  )
}
