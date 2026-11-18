# Weather-Aware Truck Routing

A React + Django app that helps a truck driver choose the **safest** route by combining
truck routing, the **hourly forecast at the moment the truck reaches each checkpoint**, the
**load weight**, and travel time.

- **Landing page** (`/`) explains the product and serves the live risk matrix.
- **Planner** (`/planner`) is the tool itself: three routes, checkpoints, risk, ETAs, the recommendation, and a 0–48 h corridor heatmap.

---

## Requirements → implementation

| Requirement | Where / how |
|---|---|
| Inputs: origin & destination, departure date/time, load weight | `PlanForm.tsx`: Photon autocomplete (keyboard accessible), datetime picker, load in lb |
| **3 route options** from a routing API | `providers/routing.py` `AlternativeRouteService`: Valhalla **truck** profile (gross weight sent) for **every trip length**. Long trips are chained truck legs (`providers/long_haul.py`), and OSRM is used only if the truck engine is down. If an engine returns fewer than 3, extra options are synthesised with perpendicular via-points and de-duplicated by geometric overlap |
| Sample weather every **10 / 25 / 50 mi** at the truck's **ETA** | `domain/sampling.py` places checkpoints by driven distance; `domain/eta.py` computes the ETA at each one; `domain/weather.py` reads the forecast at that exact time |
| Risk from the **risk/load rules** | `domain/risk.py`: thresholds and load rules are *data*; the classifier takes the worst of wind/rain/snow |
| **Recommend** the best route (risk vs time) | `domain/ranking.py`: lexicographic order from the brief, with tolerances |
| Map: all routes, checkpoints, risk, ETAs, summaries | `MapView.tsx`: MapLibre GL (WebGL). Routes, risk-coloured selected route, checkpoint dots with **ETA labels on the map**, hover/click popups (ETA, wind/gust, rain, snow, level, load-rule note), on-map route summary chips |
| Weather **heatmap** along the corridor, **0–48 h slider** | `domain/corridor.py` (grid sized to the corridor) + `services/heatmap.py` + `lib/heatmapField.ts` (renderer) + `ForecastControls.tsx` (slider from the **departure hour** to +48 h, play, Risk/Wind/Rain/Snow layers, trip-window highlight) |

---

## Risk logic (exact interpretation)

### Thresholds

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind (mph) | < 25 | 25 – <35 | 35 – <45 | 45 – <55 | **≥ 55** |
| Rain (in/hr) | < 0.10 | 0.10 – <0.25 | 0.25 – <0.50 | 0.50 – 1.00 | **> 1.00** |
| Snow (in/hr) | < 0.5 | 0.5 – <1.0 | 1.0 – <2.0 | 2.0 – 3.0 | **> 3.0** |

The brief's bands share their endpoints (for example "0.10–0.25" and "0.25–0.50"), so every band is **lower-bound inclusive**: 0.25 in/hr is High. The top band keeps the brief's own operators: "≥ 55" for wind, but "> 1.00" for rain and "> 3.0" for snow. So exactly 1.00 in/hr of rain is Severe.

### Load rules (applied to wind)

- ≥ 55 mph → No Travel for any load
- 45–54 mph **and** load > 30,000 lb → No Travel
- 35–44 mph **and** load > 40,000 lb → Severe

"> 30,000" is strict, so exactly 30,000 lb is not escalated. Every boundary is covered by parametrised tests in `backend/planner/tests/test_risk.py`.

A checkpoint's level is the **worst** of its wind, rain and snow levels. The UI shows which hazard drove it.

### Weather at the ETA

- Open-Meteo hourly data: wind in mph, rain (`rain + showers`) and snowfall in inches per hour.
- Wind is an instantaneous value, so it is **linearly interpolated** between the two surrounding hours.
- Rain and snow are accumulations over the preceding hour, so the checkpoint uses the hourly bucket whose window `(T-1h, T]` contains the ETA.

### Truck ETA model

- Valhalla's truck costing already models truck speeds and weight restrictions.
- On top of that, every segment is capped at **65 mph**, which matters only when the OSRM fallback is used.
- **FMCSA Hours of Service** are applied: a 30-minute break after 8 h of driving, and a 10-hour rest after 11 h. Late checkpoints on long trips are therefore sampled at the time the truck will *really* be there.
- The 14-hour duty window and the 70-hour cycle are not modelled.
- Speed cap, tare weight and HOS can be configured or switched off with environment variables.

### Miles per risk level

Each checkpoint represents the road between the half-way points to its neighbours, so the represented miles add up exactly to the route length. These miles feed the Severe and High totals. The **average risk** is the distance-weighted mean on a 0 (Low) … 4 (No Travel) scale.

### Recommendation

Routes are compared in this order:

1. **No-Travel miles** (added first: No Travel is strictly worse than Severe)
2. Severe miles
3. High miles
4. Average risk
5. Travel time (including HOS stops)

Exact float comparison would never let travel time decide, so each criterion has a small tolerance: 1 mile, 0.05 average-risk points, 60 s. Routes within the tolerance count as tied and the next criterion decides. Risk always dominates, and time breaks ties between equally safe routes.

The API returns which criterion decided and a human-readable reason against each other route. If **every** route crosses No-Travel conditions, the UI flags it and suggests delaying departure.

---

## Architecture

```
frontend/ (React 19 + TS, Vite)            backend/ (Django 5 + DRF)
┌──────────────────────────────┐   JSON    ┌───────────────────────────────────────────┐
│ features/landing             │ ────────▶ │ api/        views (thin) · serializers     │
│ features/planner             │           │             presenters · error envelope    │
│   components/  map/MapView   │           │ services/   TripPlanner · HeatmapService   │
│ store/ (zustand)             │           │             container (composition root)   │
│ lib/ heatmapField · geo · fmt│           │ domain/     risk · ranking · sampling · eta│
│ api/ typed client            │           │             weather · corridor · geo       │
└──────────────────────────────┘           │             (pure Python, no I/O)          │
                                           │ providers/  valhalla · osrm · open_meteo   │
                                           │             photon · cache decorators      │
                                           └───────────────────────────────────────────┘
```

- **Layered / hexagonal.** The `domain` layer is pure and deterministic. `services` orchestrate use cases against protocols in `providers/base.py`. `container.py` is the single composition root that picks the concrete adapters.
- **SOLID in practice**
  - *Single responsibility:* one concern per module (sampler, ETA model, classifier, ranker).
  - *Open/closed:* risk thresholds and load rules are data (`RiskPolicy`). New providers implement a `Protocol`.
  - *Liskov:* the caching decorators are drop-in replacements for the providers they wrap.
  - *Interface segregation:* routing, geocoding and weather each have their own small port.
  - *Dependency inversion:* `TripPlanner` depends on abstractions, and tests inject fakes.
- **Design patterns**
  - Strategy (routing providers)
  - Chain of responsibility (Valhalla → OSRM fallback; all three options always come from *one* provider so durations are comparable)
  - Decorator (caching)
  - Presenter (domain → wire format)
- **Performance**
  - All checkpoints of all routes go to the weather API in one batched, chunked, concurrent request, de-duplicated on a ~5 km grid.
  - Results are cached per point.
  - Routes render first; the heatmap loads afterwards.
  - MapLibre (about 1 MB) is code-split, so the landing page ships about 90 KB gzipped.
- **Heatmap rendering**
  - Values (not colours) are bilinearly interpolated.
  - Canvas rows are spaced in Web-Mercator, so there is no drift on long trips.
  - A blurred mask drawn from the routes clips the field to the corridor.
  - Frames are memoised and pre-rendered when the browser is idle. Scrubbing measured at about 2 display frames (33 ms) per step with no blocking work.
- **Errors.** Every API error uses `{"error": {"code", "message", "details?"}}`. Upstream failures return `502` with the provider name, unplannable requests return `422`, and validation errors return `400`.

### API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/api/plan` | `{origin, destination, departure_time, load_weight_lb, interval_miles}` → routes, checkpoints, risk, recommendation. `origin` and `destination` accept a string (geocoded on the server) or `{label, lat, lon}` |
| `POST` | `/api/heatmap` | `{routes: [[[lon,lat],…]], load_weight_lb, departure_time?}` → corridor grid with 49 hourly frames (departure → +48 h) for the `risk`, `wind`, `rain` and `snow` layers |
| `GET` | `/api/geocode?q=` | Autocomplete suggestions |
| `GET` | `/api/rules` | The risk policy as data. The landing page's risk matrix renders from this |
| `GET` | `/api/health` | Health check |

### Third-party services (all free and keyless by default)

| Concern | Service | Notes |
|---|---|---|
| Truck routing | Valhalla (`valhalla1.openstreetmap.de`) | `truck` costing with gross weight. A single request is limited to about 1,500 km, so longer trips are chained in legs |
| Long-haul corridors / fallback | OSRM (`router.project-osrm.org`) | Proposes long-haul corridors that are then truck-routed. Full fallback only if Valhalla is down |
| Weather | Open-Meteo | Set `OPEN_METEO_API_KEY` for the commercial endpoint and higher limits |
| Geocoding | Photon (OSM) | Built for type-ahead search |
| Basemap | CARTO Dark Matter (OSM data) | |

---

## Run locally

Prerequisites: Python 3.12+ and Node 20+.

```bash
# Backend (http://127.0.0.1:8000)
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # optional, all values have defaults
python manage.py runserver

# Frontend (http://localhost:5173, proxies /api → :8000)
cd frontend
npm install
npm run dev
```

### Tests and quality

```bash
cd backend  && pytest && ruff check . && ruff format --check .   # 88 tests
cd frontend && npm test && npm run lint && npm run build             # 12 unit tests
cd frontend && npx playwright install chromium && npm run test:e2e   # 16 end-to-end tests
```

The backend tests cover:
- every threshold boundary and load rule
- sampling and HOS maths
- ETA-aware weather lookup
- ranking order and tolerances
- provider parsing
- via-point alternatives and the fallback chain
- long-haul truck-leg chaining
- the request throttle and circuit breaker
- the per-day weather cache and weather budget
- the corridor grid
- the HTTP contract, including rate-limit 503 and JSON 404

The frontend unit tests cover:
- heatmap interpolation
- risk segmentation
- store actions (plan → heatmap, errors, checkpoint→slider sync)
- formatters and colour ramps

The **Playwright** end-to-end tests run on desktop and a phone viewport. Every `/api` call is intercepted with deterministic fixtures, so they never depend on live weather. They cover:
- the full flow: inputs → 3 routes → recommendation → checkpoints → heatmap
- the case where every route is blocked by No-Travel
- rate limit → retry
- a 100+ checkpoint trip with no overflow
- form validation
- the sticky header and section highlight
- the statement fill, counters and live risk matrix
- no horizontal scroll

CI runs all of it (`.github/workflows/ci.yml`).

---

## Deploy

**Vercel (recommended): see [`DEPLOY_VERCEL.md`](DEPLOY_VERCEL.md)** for the step-by-step guide.
It uses two projects from this repo: `backend/` as the Django API and `frontend/` as the React app. Upstash Redis is required there, so the cache and the 1 request/second throttle for the public routing servers are shared across serverless instances.

**Alternative: one container.** The app also ships as **one container**: the React build is served by Django/WhiteNoise, pre-compressed, with immutable caching for hashed assets.

```bash
docker build -t truck-routing .
docker run -p 8000:8000 -e DJANGO_SECRET_KEY=change-me -e DJANGO_ALLOWED_HOSTS='*' truck-routing
```

**Render (free plan):** push to GitHub, then in Render choose **New → Blueprint**, select the repo, and `render.yaml` does the rest. Any Docker host also works, for example Fly.io, Railway or Cloud Run.

| Env var | Default | Meaning |
|---|---|---|
| `DJANGO_SECRET_KEY` | dev key | **Set in production** |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1,.onrender.com` | |
| `OPEN_METEO_API_KEY` | — | Recommended for production traffic |
| `REDIS_URL` (or `KV_URL`) | — | Shared cache **and** a cross-instance throttle. **Required on Vercel** |
| `HEATMAP_MAX_NODES` | 280 | Weather lookups per heatmap. Raise it with an API key for a finer grid |
| `VALHALLA_BASE_URL` / `OSRM_BASE_URL` | public demo servers | Point at self-hosted engines for production traffic |
| `VALHALLA_MIN_INTERVAL_S` / `OSRM_MIN_INTERVAL_S` | 1.05 | Request spacing. Set to 0 for self-hosted engines |
| `TRUCK_TARE_WEIGHT_LB` / `TRUCK_MAX_SPEED_MPH` / `TRUCK_APPLY_HOS` | 33000 / 65 / true | Truck model |

---

## Operating on free public services (how it is handled)

The defaults need **no API keys**. Every free service has a usage policy, and the app is built to respect it rather than hope:

| Concern | What the app does |
|---|---|
| FOSSGIS Valhalla and OSRM demo servers allow at most **1 request/second** per client, and exceeding it gets the IP blocked | A process-wide throttle (`HostThrottle`) spaces every request at 1.05 s or more. Via-point alternatives are tried one at a time and stop as soon as 3 routes exist. Production runs **one gunicorn worker with 16 threads**, so the throttle really is global |
| Valhalla unreachable or blocking | A circuit breaker skips it for 5 minutes and falls back to OSRM immediately, with no hanging requests. Route cards then say "road routing — truck engine unavailable" |
| Open-Meteo free quota: 600 location-calls per minute | Each plan is capped at 260 weather points, using a finer lattice for regional trips and a coarser one, up to about 25 km, for cross-country trips. The heatmap is capped at 280 nodes. Forecasts are cached **per point per UTC day**, so plans, heatmaps and repeat searches share them |
| Quota exhausted anyway | The API returns `503 rate_limited` with `Retry-After: 60`, and the UI shows a plain message with a **Try again** button |
| Render free plan | Sleeps after inactivity, so the first request after idle takes about 30–60 s |

For production traffic, set `OPEN_METEO_API_KEY` and point `VALHALLA_BASE_URL` / `OSRM_BASE_URL` at self-hosted engines. Then set the `*_MIN_INTERVAL_S` values to 0 and raise `HEATMAP_MAX_NODES`. No code changes are needed.

Scope notes:
- Departures are limited to the next 10 days, and a trip must finish within the 15-day forecast horizon.
- Units are US (mph, in/hr, lb). Routing and weather work worldwide.
- The heatmap's grid spacing on very long trips follows from the weather budget: about 0.2° for regional trips and about 0.8° for 2,000-mile trips. Raising `HEATMAP_MAX_NODES` makes it finer.

---

Credits:
- Hero photo by Zoshua Colah on Unsplash (Unsplash License)
- Map data © OpenStreetMap contributors, © CARTO
- Weather by Open-Meteo (CC BY 4.0)
- Routing by Valhalla and OSRM
