# ---- 1. Build the React app ------------------------------------------------------------
FROM node:22-alpine AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Django API + static SPA (one deployable unit) -----------------------------------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FRONTEND_DIST=/app/frontend/dist \
    PORT=8000
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
COPY --from=web /app/frontend/dist /app/frontend/dist
RUN DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput >/dev/null \
    && python -m whitenoise.compress /app/frontend/dist  # pre-built .gz/.br for the SPA
RUN useradd --create-home app && chown -R app /app
USER app
EXPOSE 8000
# gthread workers: requests mostly wait on upstream APIs (I/O bound).
CMD gunicorn config.wsgi:application --bind 0.0.0.0:${PORT} --workers 2 --threads 8 --worker-class gthread --timeout 90 --access-logfile -
