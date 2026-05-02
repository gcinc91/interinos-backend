# interinos-backend

API en Python/FastAPI para la app **Interinos** — mapa de vacantes docentes de la Junta de Andalucía (SIPRI) para profesores interinos.

Sirve datos scrapeados desde [SIPRI](https://sipri.juntadeandalucia.es/sipri/plazas/plaza), geocoding de direcciones de usuario (Nominatim) y distancias por carretera (OSRM). Sin autenticación.

**Live**: https://interinos-backend.onrender.com

## Stack

- Python 3.11 + FastAPI + Uvicorn
- SQLAlchemy async + Alembic + GeoAlchemy2
- PostgreSQL + PostGIS (Supabase free tier, eu-west-1)
- httpx + tenacity (scraper SIPRI)
- APScheduler in-process opcional, GitHub Actions cron en producción

## Setup local

Requiere Python 3.11 y [uv](https://github.com/astral-sh/uv).

```bash
uv sync --extra dev
cp .env.example .env       # rellena DATABASE_URL (Supabase pooler)
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

API en `http://localhost:8000`. Docs interactivas en `/docs`.

### Tests

```bash
uv run pytest -q                # 49 tests, sin live
uv run pytest -m live           # smoke real contra SIPRI
uv run ruff check app tests     # lint
uv run mypy app                 # type check
```

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/vacancies/version` | Hash + last_run_at + items_active |
| GET | `/vacancies` | Lista filtrada (lat,lon,radius_km,bbox,cuerpo[],provincia[]…) |
| GET | `/vacancies/{id}` | Detalle |
| GET | `/filters` | Cuerpos / especialidades / provincias / tipos / participaciones |
| POST | `/geocode` | Geocoding de dirección de usuario (Nominatim, cache) |
| POST | `/distance` | Matriz origen→destinos (OSRM Table + fallback haversine + cache) |
| POST | `/admin/scrape` | Trigger manual del sync (header `X-Admin-Token`) |

## Variables de entorno

| Variable | Descripción | Por defecto |
|---|---|---|
| `DATABASE_URL` | postgres+asyncpg URL al Supabase pooler | — (obligatoria) |
| `SIPRI_BASE_URL` | base URL de la fuente SIPRI | https://sipri.juntadeandalucia.es |
| `NOMINATIM_BASE_URL` | base URL Nominatim | https://nominatim.openstreetmap.org |
| `OSRM_BASE_URL` | base URL OSRM Table | https://router.project-osrm.org |
| `USER_AGENT` | UA identificable (política Nominatim) | InterinosBot/1.0 |
| `CORS_ORIGIN` | orígenes permitidos (CSV) | http://localhost:5173 |
| `CORS_ORIGIN_REGEX` | regex adicional, p.ej. `^https://.*\.vercel\.app$` | — |
| `ADMIN_TOKEN` | token requerido por `/admin/scrape` | change-me (rechazado) |
| `ENABLE_SCHEDULER` | arrancar APScheduler in-process | true |
| `SCRAPE_CRON` | expresión cron (Europe/Madrid) | `0 */6 * * *` |
| `LOG_LEVEL` | nivel de logging structlog | INFO |

## Deploy (producción)

### Backend → Render free

1. Importa este repo en Render como **Blueprint** → lee [`render.yaml`](./render.yaml) automáticamente.
2. Pega `DATABASE_URL` (Supabase pooler) y `CORS_ORIGIN` (URLs Vercel/local). `ADMIN_TOKEN` se autogenera.
3. `ENABLE_SCHEDULER=false` en Render: el web free duerme tras 15 min idle, así que el cron in-process no es fiable. El sync periódico lo dispara GitHub Actions.

### Cron periódico → GitHub Actions

[`.github/workflows/scrape.yml`](./.github/workflows/scrape.yml) corre `0 */6 * * *` UTC. Despierta el backend con `/health` y luego hace `POST /admin/scrape`.

Configura los secrets del repo:

```bash
gh secret set BACKEND_URL --body "https://interinos-backend.onrender.com"
gh secret set ADMIN_TOKEN --body "<el ADMIN_TOKEN de Render>"
```

Trigger manual:

```bash
gh workflow run "scrape-sipri"
```

## Troubleshooting

- **Direct connect Supabase falla con DNS**: free tier sólo IPv6 en `db.<ref>.supabase.co`. Usa el **Session Pooler** (host `aws-0-<region>.pooler.supabase.com`, puerto 5432, user `postgres.<ref>`) o el **Transaction Pooler** (puerto 6543) con `statement_cache_size=0` (ya configurado en `app/db/session.py`).
- **Cold start Render free** ~30-60 s tras 15 min idle. Las llamadas del workflow incluyen retry con backoff.
- **Hatchling falla en build Docker** por `README.md` ausente: el `Dockerfile` lo copia explícitamente; mantén `readme = "README.md"` en `pyproject.toml`.

## Frontend

[interinos-frontend](https://github.com/gcinc91/interinos-frontend) — Vite + React + TypeScript + Leaflet.

## Licencia

Apache 2.0 — ver [LICENSE](LICENSE).
