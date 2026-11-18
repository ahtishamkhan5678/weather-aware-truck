# Deploy on Vercel: backend and frontend

You will create **two Vercel projects from the same GitHub repo**:

| Project | Root directory | What it is | Example URL |
|---|---|---|---|
| `weather-aware-api` | `backend` | Django API (one Python serverless function) | `https://weather-aware-api.vercel.app` |
| `weather-aware-web` | `frontend` | React app (static files on Vercel's CDN) | `https://weather-aware-web.vercel.app` |

The order matters: **backend → Redis → frontend → connect them**. Total time is about 20 minutes.

> Your real URLs depend on the project names you choose. Wherever this guide says
> `weather-aware-api.vercel.app` or `weather-aware-web.vercel.app`, use **your** URLs.

---

## 0. Before you start

- [ ] The code is on GitHub (see the README or ask for the push step).
- [ ] You have a Vercel account. Sign up at https://vercel.com with **Continue with GitHub**; the free Hobby plan is enough.
- [ ] Generate a Django secret key and keep it for step 1.5:
  ```bash
  python3 -c "import secrets; print(secrets.token_urlsafe(50))"
  ```

---

## 1. Backend project (Django API)

1. Go to https://vercel.com/new and click **Import** next to your GitHub repository. The first time, click **Adjust GitHub App Permissions** and allow the repo.
2. **Project Name:** `weather-aware-api`
3. **Root Directory:** click **Edit**, choose **`backend`**, then **Continue**.
4. **Framework Preset:** it should show **Django** automatically, because Vercel finds `backend/manage.py`. Leave the Build and Output settings as they are.
5. Open **Environment Variables** and add:

   | Key | Value |
   |---|---|
   | `DJANGO_SECRET_KEY` | the key you generated in step 0 |
   | `DJANGO_DEBUG` | `false` |
   | `DJANGO_ALLOWED_HOSTS` | `.vercel.app` |
   | `CORS_ALLOWED_ORIGINS` | `http://localhost:5173` (temporary; you'll replace it in step 4) |

6. Click **Deploy** and wait for "Congratulations".
7. **Test it:** open `https://weather-aware-api.vercel.app/api/health`. You should see:
   ```json
   {"status":"ok"}
   ```
   Also open `/api/rules`, which should return the risk thresholds as JSON.

### What the repo already configures for you

- `backend/vercel.json` lets each request run for up to **60 s**, which long trips need, and leaves test files out of the bundle.
- `backend/.python-version` pins **Python 3.12**.
- `backend/requirements.txt` holds the runtime dependencies.

---

## 2. Add Redis (required for the backend)

Vercel runs the backend as **many short-lived instances**. Without a shared store, each instance would have its own cache and its own request throttle. The public routing servers allow **1 request/second**, and exceeding that gets the server IP **blocked**, which we've seen happen. Redis makes the cache and the throttle shared by every instance.

1. Open the **weather-aware-api** project, then the **Storage** tab, then **Create Database** (or browse the **Marketplace**).
2. Choose **Upstash → Redis**, pick the **Free** plan, choose a region close to your users (for example `us-east-1`), and create it.
3. When asked to connect it to a project, choose **weather-aware-api** and tick **all environments**. This adds a `REDIS_URL` or `KV_URL` variable; the app accepts either.
4. Go to **Deployments**, click **⋯** on the latest deployment, then **Redeploy**. Environment variables apply only to new deployments.
5. **Check:** `/api/health` still says `{"status":"ok"}`.

---

## 3. Frontend project (React)

1. Go to https://vercel.com/new and **Import** the **same** repository again.
2. **Project Name:** `weather-aware-web`
3. **Root Directory:** **Edit**, then **`frontend`**.
4. **Framework Preset:** **Vite** is detected. Leave the build command (`npm run build`) and output directory (`dist`) as they are; `frontend/vercel.json` sets them too.
5. **Environment Variables:** add one:

   | Key | Value |
   |---|---|
   | `VITE_API_BASE` | `https://weather-aware-api.vercel.app/api` |

   Use your backend URL from step 1, **ending in `/api`**.

   > Vite bakes this value into the build. If you ever change it, you must **Redeploy** the frontend.

6. Click **Deploy**.
7. **Test it:** open `https://weather-aware-web.vercel.app`. The landing page should load and the **Risk matrix** at the bottom should show the table. That table comes from the API, so if it appears, the frontend can reach the backend's `/api/rules`.

---

## 4. Connect them (CORS)

The browser only lets the frontend call the backend if the backend allows the frontend's address.

1. Open **weather-aware-api**, then **Settings → Environment Variables**.
2. Edit `CORS_ALLOWED_ORIGINS` and set it to your frontend URL, **with no trailing slash**:
   ```
   https://weather-aware-web.vercel.app
   ```
   If you also have a custom domain, separate the entries with a comma: `https://weather-aware-web.vercel.app,https://your-domain.com`
3. *(Optional)* To let **preview** deployments of the frontend work too, add:

   | Key | Value |
   |---|---|
   | `CORS_ALLOWED_ORIGIN_REGEXES` | `^https://weather-aware-web(-[a-z0-9-]+)?\.vercel\.app$` |

4. **Redeploy** the backend (Deployments → ⋯ → Redeploy).

---

## 5. Verify the whole flow on the live site

Open `https://weather-aware-web.vercel.app/planner` and follow the **Quick demo** in `TESTING.md`:

- [ ] Typing `Denver` shows autocomplete suggestions. That proves geocoding works through the API.
- [ ] **Denver → Salt Lake City → Find the safest route** shows 3 routes in about 5–15 s, with recommendation, checkpoints and ETA labels.
- [ ] The heatmap appears and the slider and Play work.
- [ ] Reloading the browser on `/planner` still shows the planner, not a 404. The SPA rewrite handles this.
- [ ] Route cards say **"truck routing (weight-aware)"**. If they say "road routing — truck engine unavailable", the public truck server is busy or blocking; the app falls back to OSRM and retries truck routing automatically after 5 minutes.
- [ ] Phone check: open the URL on your phone.

The first request after a quiet period can take a few extra seconds, because a function instance has to start ("cold start"). That's normal.

---

## 6. Optional but recommended

| Variable (backend) | Why |
|---|---|
| `OPEN_METEO_API_KEY` | Removes the free-tier weather limit of 600 location-calls per minute. Get a key at https://open-meteo.com/en/pricing |
| `HEATMAP_MAX_NODES` | Raise it, for example to `1200`, **only with an API key**, for a finer heatmap on long trips |
| `VALHALLA_BASE_URL`, `OSRM_BASE_URL` | Point at self-hosted routing engines for heavy traffic, then set `VALHALLA_MIN_INTERVAL_S=0` and `OSRM_MIN_INTERVAL_S=0` |

Every push to `main` now redeploys **both** projects automatically. Each push to another branch gets its own preview URL.

---

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Browser console says **"blocked by CORS policy"** | `CORS_ALLOWED_ORIGINS` doesn't exactly match the frontend URL | Use the exact URL with `https://` and no trailing `/`, then **Redeploy the backend** |
| Planner shows **"Cannot reach the server"** | `VITE_API_BASE` is wrong or missing | Set it to `https://<backend>.vercel.app/api`, then **Redeploy the frontend** |
| `/api/health` returns **400 Bad Request** | Host not allowed | `DJANGO_ALLOWED_HOSTS=.vercel.app` (include the leading dot), then redeploy |
| **504 / "Function timed out"** on very long trips | Over 60 s, because the public servers allow only 1 request/second | Retry; a second identical search is cached. Use self-hosted engines for heavy use |
| "The free weather quota is busy right now…" | Open-Meteo free limit reached | Wait about 1 minute and click **Try again**, or add `OPEN_METEO_API_KEY` |
| Build fails with "maxDuration" | Your plan's limit is lower than 60 s | Lower `maxDuration` in `backend/vercel.json` |
| Changes don't appear | Environment variables only apply to **new** deployments | Redeploy the project |

---

### Alternative: one container instead of two projects

If you prefer a single always-on server, the repo also includes a `Dockerfile` and `render.yaml`; see README → Deploy. On that path Redis is optional, because the single process shares its cache and throttle.
