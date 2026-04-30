"""Geocoding de direcciones del usuario via Nominatim (OSM), con cache en BD.

Las vacantes ya vienen geo-localizadas desde SIPRI. Este servicio solo geocoda
la dirección de input del usuario para centrar el mapa.

Política de Nominatim: 1 req/s, identificarse con User-Agent. La aplicamos con
un `asyncio.Lock` global más un timestamp del último call.
"""
from __future__ import annotations

import asyncio
from time import monotonic

import httpx
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import GeocodeCache

log = get_logger(__name__)

# Bounding box de Andalucía. Orden Nominatim viewbox: lon_min, lat_max, lon_max, lat_min.
ANDALUSIA_VIEWBOX = "-7.6,38.8,-1.5,35.9"

_nominatim_lock: asyncio.Lock | None = None
_nominatim_last_call: float = 0.0


def _get_nominatim_lock() -> asyncio.Lock:
    global _nominatim_lock
    if _nominatim_lock is None:
        _nominatim_lock = asyncio.Lock()
    return _nominatim_lock


def normalize_address(address: str) -> str:
    """Lowercase, colapsa espacios. Añade ", andalucía, españa" si no hay
    ningún hint geográfico — mejora drásticamente la precisión de Nominatim
    para inputs cortos como `"sevilla"`.
    """
    cleaned = " ".join(address.lower().split())
    if not any(token in cleaned for token in ("andalu", "españa", "spain", "spagna")):
        cleaned = f"{cleaned}, andalucía, españa"
    return cleaned


class NominatimClient:
    """Cliente Nominatim con rate-limit global 1 req/s y bbox Andalucía."""

    def __init__(self, base_url: str, user_agent: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.user_agent = user_agent

    async def search(self, query: str) -> tuple[float, float] | None:
        global _nominatim_last_call
        lock = _get_nominatim_lock()
        async with lock:
            wait = 1.0 - (monotonic() - _nominatim_last_call)
            if wait > 0:
                await asyncio.sleep(wait)
            try:
                async with httpx.AsyncClient(
                    base_url=self.base_url,
                    timeout=httpx.Timeout(15.0, connect=5.0),
                    headers={"User-Agent": self.user_agent},
                ) as client:
                    response = await client.get(
                        "/search",
                        params={
                            "q": query,
                            "format": "json",
                            "limit": "1",
                            "countrycodes": "es",
                            "viewbox": ANDALUSIA_VIEWBOX,
                            "bounded": "1",
                            "addressdetails": "0",
                        },
                    )
                    response.raise_for_status()
                    results = response.json()
            finally:
                _nominatim_last_call = monotonic()

        if not results:
            return None
        first = results[0]
        try:
            return float(first["lat"]), float(first["lon"])
        except (KeyError, ValueError, TypeError):
            return None


class GeocodeService:
    def __init__(
        self,
        session: AsyncSession,
        nominatim: NominatimClient | None = None,
    ) -> None:
        self.session = session
        if nominatim is None:
            settings = get_settings()
            nominatim = NominatimClient(
                base_url=settings.NOMINATIM_BASE_URL,
                user_agent=settings.USER_AGENT,
            )
        self.nominatim = nominatim

    async def geocode(self, address: str) -> tuple[float, float, str, bool] | None:
        """Devuelve `(lat, lon, address_norm, cached)` o `None` si no se encuentra."""
        norm = normalize_address(address)

        cached = await self.session.execute(
            select(GeocodeCache).where(GeocodeCache.address_norm == norm)
        )
        row = cached.scalar_one_or_none()
        if row is not None:
            log.info("geocode_cache_hit", address_norm=norm)
            return float(row.lat), float(row.lon), norm, True

        log.info("geocode_cache_miss", address_norm=norm)
        coords = await self.nominatim.search(norm)
        if coords is None:
            log.info("geocode_not_found", address_norm=norm)
            return None
        lat, lon = coords

        stmt = (
            pg_insert(GeocodeCache)
            .values(address_norm=norm, lat=lat, lon=lon, provider="nominatim")
            .on_conflict_do_update(
                index_elements=["address_norm"],
                set_={"lat": lat, "lon": lon, "fetched_at": func.now()},
            )
        )
        await self.session.execute(stmt)
        await self.session.commit()
        return lat, lon, norm, False
