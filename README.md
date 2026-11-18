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
| **3 route options** from a routing API | `providers/routing.py` `AlternativeRouteService`: Valhalla **truck** profile (gross weight sent), OSRM fallback. If an engine returns fewer than 3, extra options are synthesised with perpendicular via-points and de-duplicated by geometric overlap |
| Sample weather every **10 / 25 / 50 mi** at the truck's **ETA** | `domain/sampling.py` places checkpoints by driven distance; `domain/eta.py` computes the ETA at each one; `domain/weather.py` reads the forecast at that exact time |
| Risk from the **risk/load rules** | `domain/risk.py`: thresholds and load rules are *data*; the classifier takes the worst of wind/rain/snow |
| **Recommend** the best route (risk vs time) | `domain/ranking.py`: lexicographic order from the brief, with tolerances |
| Map: all routes, checkpoints, risk, ETAs, summaries | `MapView.tsx`: MapLibre GL (WebGL). Routes, risk-coloured selected route, checkpoint dots with hover/click popups (ETA, wind/gust, rain, snow, level, load-rule note), on-map route summary chips |
| Weather **heatmap** along the corridor, **0–48 h slider** | `services/heatmap.py` (corridor grid) + `lib/heatmapField.ts` (renderer) + `ForecastControls.tsx` (slider, play, Risk/Wind/Rain/Snow layers, trip-window highlight) |

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
- On top of that, every segment is capped at **65 mph**, which matters for OSRM car timings.
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
| `POST` | `/api/heatmap` | `{routes: [[[lon,lat],…]], load_weight_lb}` → corridor grid with 49 hourly frames for the `risk`, `wind`, `rain` and `snow` layers |
| `GET` | `/api/geocode?q=` | Autocomplete suggestions |
| `GET` | `/api/rules` | The risk policy as data. The landing page's risk matrix renders from this |
| `GET` | `/api/health` | Health check |

### Third-party services (all free and keyless by default)

| Concern | Service | Notes |
|---|---|---|
| Truck routing | Valhalla (`valhalla1.openstreetmap.de`) | `truck` costing with gross weight. The public server is limited to about 1,500 km |
| Long-haul routing / fallback | OSRM (`router.project-osrm.org`) | Car profile, corrected by the truck ETA model |
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
cd backend  && pytest && ruff check . && ruff format --check .   # 75 tests
cd frontend && npm test && npm run lint && npm run build
```

The backend tests cover:
- every threshold boundary and load rule
- sampling and HOS maths
- ETA-aware weather lookup
- ranking order and tolerances
- provider parsing
- via-point alternatives and the fallback chain
- the HTTP contract

The frontend tests cover heatmap interpolation and risk segmentation. CI runs everything (`.github/workflows/ci.yml`).

---

## Deploy

The app ships as **one container**: the React build is served by Django/WhiteNoise, pre-compressed, with immutable caching for hashed assets.

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
| `REDIS_URL` | — | Shared cache across workers or instances |
| `TRUCK_TARE_WEIGHT_LB` / `TRUCK_MAX_SPEED_MPH` / `TRUCK_APPLY_HOS` | 33000 / 65 / true | Truck model |

---

## Known limitations (stated plainly)

- **Free-tier rate limits.**
  - Open-Meteo counts every location in a request toward its free quota. A long trip at 10-mile sampling plus the heatmap uses a few hundred location-calls.
  - Caching absorbs repeated searches, but many cold searches per minute can trigger HTTP 429. The client retries with back-off, and an API key removes the limit.
  - The public Valhalla and OSRM demo servers are best-effort.
- **Trips over about 930 mi** use OSRM, which has a car profile; durations are corrected with the truck speed cap and HOS. The provider is shown on every route card.
- **Forecast horizon.** Departures are limited to the next 10 days, and a trip must finish within the 15-day horizon.
- **US-centric copy and units** (mph, inches, lb). Routing and weather work worldwide.

---

Credits:
- Hero photo by Zoshua Colah on Unsplash (Unsplash License)
- Map data © OpenStreetMap contributors, © CARTO
- Weather by Open-Meteo (CC BY 4.0)
- Routing by Valhalla and OSRM
