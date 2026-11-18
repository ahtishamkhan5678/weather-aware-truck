# Testing Guide — Weather-Aware Truck Routing

This guide checks every requirement in the assignment, step by step. Each test lists **what to do** and **what you should see**. Tick the box when it passes.

> Weather is live, so exact numbers change from hour to hour. These tests check *behaviour*, not specific values.

---

## ⚡ Quick demo — the complete flow in 5 minutes

Run this first. It touches every requirement once. Section 1 onward is the detailed checklist.

1. **Landing page.** Open http://localhost:5173.
   - Hover the nav pill: the black pill slides.
   - Scroll down: the statement words fill grey → white, the "Built on Clear Risk Rules" icons pop in, "49" and "5" count up, and the risk matrix appears.
2. **Planner.** Click **Plan Route ↗** (top right).
3. **Inputs.**
   - Type `Denver` in Origin and press **Enter** on "Denver, Colorado, US".
   - Type `Salt Lake City` in Destination and press **Enter**.
   - Keep the departure, load **42000**, interval **25 mi**.
4. Click **Find the safest route ↗**. After about 3–6 s you should see:
   - **3 routes** on the map, each with a summary chip (miles · time · worst level · ETA). The ★ marks the recommended route.
   - The white **Recommended** card, with the reason it won and one line comparing it to each other route.
   - The heatmap appears along the corridor after a further 1–3 s.
5. **Risk on the map.**
   - Click the chip of a route whose worst level is **High/Severe**. Its line turns risk-coloured.
   - Hover an orange or red dot. The popup shows the ETA, wind (gust), rain, snow and the level. If the load rule applied, it shows a red note such as *"Wind 35–44 mph with load >40,000 lb"*.
6. **Load rule.**
   - Change **Load** to `30000` and plan again.
   - Select the same route. The checkpoint that was **Severe** at 35–44 mph is now **High**, and the route's worst level drops too.
7. **Checkpoints.**
   - Scroll the left panel. The cards show Severe+/High miles, average risk and HOS breaks.
   - The table lists a checkpoint every 25 mi with its **ETA**.
   - Click a row: the map popup opens there and the **slider jumps to that ETA hour**.
8. **Heatmap.**
   - Click **Wind**, then press **▶**. The forecast animates 0 → 48 h. Press **❚❚** to pause.
   - Drag the slider. The yellow band on the track is the selected route's trip window.
9. **Intervals.** Switch to **10 mi** and then **50 mi**, re-planning each time. The checkpoint count changes about 5× from 10 mi to 50 mi.
10. **Mobile.**
    - DevTools → device toolbar → iPhone.
    - The order is form → map → results, with no sideways scroll. After planning, the page scrolls to the map.

> Seen live on 18 Nov 2026 at 22:00: Route C (I-80, Wyoming) had **Severe** checkpoints at 35 mph with a 42,000 lb load. At 30,000 lb they became **High**, and the app recommended Route A with "75 fewer High miles". The weather changes, so use the **Wind** heatmap with ▶ to find active areas (section 5b).

---

## 0. Start the app

You need two terminals.

```bash
# Terminal 1 — backend (API on :8000)
cd backend
source .venv/bin/activate
python manage.py runserver

# Terminal 2 — frontend (app on :5173)
cd frontend
npm run dev
```

Open **http://localhost:5173**.

- [ ] `curl localhost:8000/api/health` returns `{"status":"ok"}`

---

## 1. Automated tests (run these first)

```bash
cd backend  && source .venv/bin/activate && pytest -v
cd frontend && npm test && npm run lint && npm run build
```

- [ ] Backend: **75 passed**. These cover every risk threshold boundary, every load rule, sampling, ETA/HOS maths, ranking order, the providers and the API.
- [ ] Frontend: **5 passed**, lint is clean, and the build succeeds.

These tests prove the rules are correct even when the live weather is calm.

---

## 2. Inputs (origin, destination, departure, load)

Open **http://localhost:5173/planner**.

| # | Do | Expect |
|---|---|---|
| 2.1 | Type `Amar` in **Origin** | After about 0.3 s a dropdown shows "Amarillo, Texas, US" and other matches |
| 2.2 | Use **↓ / ↑** then **Enter** | The highlighted suggestion is selected and the dropdown closes |
| 2.3 | Pick a destination, for example `Oklahoma City` | It is selected |
| 2.4 | Click **⇅** (swap) | Origin and destination swap |
| 2.5 | Look at **Departure** | Defaults to the next whole hour; past dates are blocked |
| 2.6 | Look at **Load weight** | Defaults to 42,000 lb; accepts 0–100,000 |
| 2.7 | Clear Origin | The **Find the safest route** button is disabled |

- [ ] All of the above pass

---

## 3. Three route options

Click the preset **Denver → Salt Lake City**, then **Find the safest route ↗**.

| # | Expect |
|---|---|
| 3.1 | The button shows "Scoring routes against the forecast…" and a skeleton appears in the panel |
| 3.2 | **Exactly 3 route cards (A, B, C)** appear, and **3 lines** appear on the map |
| 3.3 | Each card shows the main roads (e.g. "I 70 · I 15"), distance, trip time and arrival |
| 3.4 | Card subtitle says **"via truck routing"**. Valhalla's truck profile was used, with the load weight sent |
| 3.5 | Repeat with a long trip (type `Los Angeles` → `Chicago`). There are still **3 routes**, and the subtitle says "via road routing" (OSRM fallback, because the trip is over about 930 mi) |

- [ ] 3 distinct routes on both trips

---

## 4. Weather sampled every 10 / 25 / 50 miles at the truck's ETA

With Denver → Salt Lake City planned:

| # | Do | Expect |
|---|---|---|
| 4.1 | Select **25 mi** and plan | The checkpoint table shows **Mile 0, 25, 50, 75 …** and the destination as the last row |
| 4.2 | Select **10 mi** and plan again | About 2.5× more checkpoints (0, 10, 20 …) and more dots on the map |
| 4.3 | Select **50 mi** and plan again | Fewer checkpoints (0, 50, 100 …) |
| 4.4 | Read the **ETA** column | ETAs increase down the table. The first equals your departure time; the last equals the card's **Arrive** time |
| 4.5 | Change **Departure** to 6 hours later and plan | Every ETA moves about 6 h later, and the weather values change. This shows the forecast is read **at the truck's ETA**, not "now" |
| 4.6 | Plan Los Angeles → Chicago | The card says "Includes … 30-min break … 10-h rest (HOS)". ETAs jump by about 10 h at the rest stops |

- [ ] Intervals, ETAs and departure-time sensitivity all correct

---

## 5. Risk classification (risk and load rules)

### 5a. Check a checkpoint by hand

1. Hover any checkpoint dot on the map. A popup shows the ETA, wind (with gust), rain, snow and the **risk level**.
2. Compare it with the table below, which is the same as the brief:

| Condition | Low | Moderate | High | Severe | No Travel |
|---|---|---|---|---|---|
| Wind | <25 mph | 25–34 | 35–44 | 45–54 | ≥55 |
| Rain | <0.10 in/hr | 0.10–0.25 | 0.25–0.50 | 0.50–1.00 | >1.00 |
| Snow | <0.5 in/hr | 0.5–1.0 | 1.0–2.0 | 2.0–3.0 | >3.0 |

- [ ] The level equals the **worst** of wind, rain and snow. Underlined values in the table are the hazard that set the level.

### 5b. Find real bad weather (calm weather only shows Low)

1. Plan a trip, open the heatmap panel at the bottom of the map, and choose **Wind** or **Rain**.
2. Press **▶ play**. Note *when* and *where* the colours turn orange or red.
3. Plan a trip through that area, and set the **departure** so the truck reaches it at that hour.

Areas that were active when this guide was written (they will change):
- **San Francisco → Los Angeles via the coast:** wind up to about 38 mph and rain up to about 0.5 in/hr
- **Reno → Boise:** snow up to about 1 in/hr

### 5c. Load rules (the key test)

Pick a trip where some checkpoint has **wind between 35 and 44 mph** (it shows High at a light load).

| # | Load | Expect at that checkpoint |
|---|---|---|
| 5c.1 | **30,000 lb** | **High** |
| 5c.2 | **45,000 lb** | **Severe**; the popup note says "Wind 35–44 mph with load >40,000 lb" |

If a checkpoint has wind of **45–54 mph**:

| Load | Expect |
|---|---|
| 30,000 lb | **Severe** |
| 35,000 lb | **No Travel** |

Any checkpoint with wind of **55 mph or more** is **No Travel** at any load.

- [ ] Load changes escalate risk as stated

If the live weather has no wind that strong, the same rules are proven by the tests in `backend/planner/tests/test_risk.py::test_load_rules`. You can also check them through the API:

```bash
curl -s localhost:8000/api/rules | python3 -m json.tool
```

---

## 6. Recommendation (risk vs travel time)

| # | Check | Expect |
|---|---|---|
| 6.1 | The white **Recommended** card | Names the route and says **why**, e.g. "Chosen for *fewest Severe miles*", or "*shortest travel time (risk tied)*" when all routes are equally safe |
| 6.2 | The reasons list | One line for each other route, e.g. "vs Route A: 3 min faster with equal risk" or "vs Route B: 38 fewer Severe miles" |
| 6.3 | Card order | Cards are sorted by rank (#1, #2, #3). The best route has a **BEST** badge and ★ on the map |
| 6.4 | Calm weather | Severe and High miles are 0 on every route, so the **fastest** route wins |
| 6.5 | Bad weather on one route (use 5b) | The route with **fewer Severe miles wins even if it is slower**. Then High miles decide, then average risk, then time |
| 6.6 | Totals | On each card, the coloured risk bar's segments add up to the route distance |

- [ ] The recommendation follows the order Severe → High → average risk → time

---

## 7. Map: routes, checkpoints, risk, ETAs, summaries

| # | Do | Expect |
|---|---|---|
| 7.1 | Look at the map | 3 routes. The selected one is coloured **by risk** (green, yellow, orange, red, purple); the others are grey |
| 7.2 | Route summary chips on the map | Each shows "A · 491 mi · 9h 01m · Moderate max · ETA 06:01" |
| 7.3 | Click a different route (chip, line or card) | It becomes highlighted and the checkpoint table switches to it |
| 7.4 | Hover a checkpoint dot | Popup: route and checkpoint number, ETA, mile, wind/gust, rain, snow, level |
| 7.5 | Click a row in the checkpoint table | The map shows that checkpoint's popup and pans to it, and the **slider jumps to that ETA hour** |
| 7.6 | Click a segment of the coloured timeline strip | Same as 7.5 |
| 7.7 | Origin and destination | White dot = origin, black dot = destination |

- [ ] All visible and interactive

---

## 8. Weather heatmap with 0–48 h slider

| # | Do | Expect |
|---|---|---|
| 8.1 | After planning, wait 1–3 s | "Building 48-hour corridor forecast…", then a coloured overlay **only along the route corridor** |
| 8.2 | Drag the slider from 0 to 48 | The overlay changes every hour **smoothly, with no flicker or freeze**. The label shows the date/time and "+N h" |
| 8.3 | Press **▶** | It animates through 48 h and loops; **❚❚** pauses |
| 8.4 | Switch **Risk / Wind / Rain / Snow** | The overlay and the legend (scale and units) change |
| 8.5 | The yellow band on the slider track | Marks the selected route's departure → arrival window |
| 8.6 | **Hide heatmap** | The overlay toggles off and on |
| 8.7 | Zoom and pan the map | The overlay stays aligned with the roads |

- [ ] Smooth, with no console errors (DevTools → Console)

---

## 9. Error handling

| # | Do | Expect |
|---|---|---|
| 9.1 | Origin `Honolulu`, destination `Chicago` | Red message: "No drivable truck route connects these places…" |
| 9.2 | Origin text `asdfqwer zzz` (don't pick a suggestion), then plan | "Could not find the origin …" |
| 9.3 | Stop the backend (Ctrl+C), then plan | "Cannot reach the server…" or an upstream error message. The app does not crash |
| 9.4 | API validation | `curl -s -X POST localhost:8000/api/plan -H 'Content-Type: application/json' -d '{"origin":"Dallas","destination":"Austin","departure_time":"2030-01-01T00:00:00Z","load_weight_lb":40000,"interval_miles":15}'` returns a 400 with `invalid_request` |

- [ ] Errors are clear and the app recovers

---

## 10. Landing page and responsive design

| # | Do | Expect |
|---|---|---|
| 10.1 | Open `/` | The hero loads with animations: the title rises, the photo un-blurs, and the counters "3" and "48h" count up |
| 10.2 | Hover the nav pill | The black pill slides to the hovered link |
| 10.3 | Scroll down | The statement words fill from grey to white as you scroll |
| 10.4 | Reach "Built on Clear Risk Rules" | The icons pop in, and "49" and "5" count up |
| 10.5 | Risk matrix | Matches the brief exactly. It is loaded from the API |
| 10.6 | DevTools → device toolbar → iPhone (390 px) | One-column layout with **no sideways scrolling**, on both `/` and `/planner` |
| 10.7 | Turn on OS "Reduce motion" | No animations; everything is shown filled and counted |

- [ ] Landing page and mobile look correct

---

## 11. Production build (how it will run when hosted)

```bash
cd frontend && npm run build
cd ../backend && source .venv/bin/activate
python manage.py collectstatic --noinput
DJANGO_DEBUG=false DJANGO_SECRET_KEY=test gunicorn config.wsgi:application --bind 127.0.0.1:8001
```

Open **http://127.0.0.1:8001**. The whole app (frontend and API) runs from one server.

- [ ] Landing page, planner and a full trip plan all work on :8001

---

## 12. Ready to push?

- [ ] Sections 1–11 all ticked
- [ ] `git status` shows no `.env`, `node_modules`, `.venv` or `dist` files

When everything passes, push and deploy (see `README.md` → Deploy).

---

### Troubleshooting

| Symptom | Cause / fix |
|---|---|
| "A data provider (open-meteo) is unavailable" | Free weather rate limit after many searches. Wait about 1 minute, or set `OPEN_METEO_API_KEY` |
| Plan takes over 10 s | The public routing servers are slow; retry. A second identical search is cached. Intercontinental trips (for example London → Kathmandu, about 6,000 mi) take 20–40 s because of their size |
| Map is blank | Check your internet connection (map tiles come from CARTO) |
| Everything is "Low" | The weather really is calm. Use section 5b to find active weather |
