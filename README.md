# interinos-backend

API en Python/FastAPI para la app **Interinos** — mapa de vacantes docentes de la Junta de Andalucía (SIPRI) para profesores interinos.

Sirve datos scrapeados desde [SIPRI](https://sipri.juntadeandalucia.es/sipri/plazas/plaza), geocoding de direcciones de usuario (Nominatim) y distancias por carretera (OSRM). Sin autenticación.

## Stack

- Python 3.11 + FastAPI + Uvicorn
- SQLAlchemy async + Alembic
- PostgreSQL 15 + PostGIS (Supabase)
- httpx + tenacity (scraper SIPRI)
- APScheduler (cron 6h)

## Setup local

Requiere Python 3.11 y [uv](https://github.com/astral-sh/uv).

```bash
uv sync
cp .env.example .env  # rellenar DATABASE_URL etc.
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

API en `http://localhost:8000`. Docs en `/docs`.

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/health` | Liveness |
| GET | `/vacancies/version` | Hash de la última versión de datos |
| GET | `/vacancies` | Lista filtrada y ordenada por distancia |
| GET | `/vacancies/{id}` | Detalle |
| POST | `/geocode` | Geocoding de dirección de usuario (Nominatim, cacheado) |
| POST | `/distance` | Distancia por carretera origen→destinos (OSRM, cacheado) |
| GET | `/filters` | Cuerpos / especialidades / provincias disponibles |
| POST | `/admin/scrape` | Trigger manual de scrape (header `X-Admin-Token`) |

## Frontend

[interinos-frontend](https://github.com/gcinc91/interinos-frontend) — Vite + React + TypeScript + Leaflet.

## Licencia

Apache 2.0 — ver [LICENSE](LICENSE).
