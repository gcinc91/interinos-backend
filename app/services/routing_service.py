"""Distancia por carretera vía OSRM público + cache + fallback haversine.

OSRM Table API: `GET /table/v1/driving/{coords}?sources=0&destinations=1;2;...&annotations=distance,duration`
Coordenadas: `lon,lat` separados por `;`. Limita el batch a ~100 destinos.

Estrategia:
1. Para cada destino: lookup en `distance_cache` por par (origen, dest) redondeado.
2. Los que faltan → un único POST/GET batch a OSRM Table.
3. Cualquier fallo (red, code != Ok, valores null) → fallback haversine.
4. Resultados OSRM exitosos → upsert en cache.

`straight_distance_km` siempre se devuelve (haversine), independientemente de la
fuente de la distancia por carretera, para usarla como sort estable cuando OSRM
no esté disponible.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import httpx
from sqlalchemy import and_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import DistanceCache
from app.schemas.distance import DistanceDestination, DistanceResult

log = get_logger(__name__)

EARTH_RADIUS_KM = 6371.0
COORD_PRECISION = 5  # ~1m a esta latitud
OSRM_TIMEOUT_S = 15.0
OSRM_MAX_DESTINATIONS = 100


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    rlat1 = math.radians(lat1)
    rlat2 = math.radians(lat2)
    dlat = rlat2 - rlat1
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(rlat1) * math.cos(rlat2) * math.sin(dlon / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def _round_coord(value: float) -> float:
    return round(value, COORD_PRECISION)


@dataclass(frozen=True, slots=True)
class _RoundedKey:
    origin_lat: float
    origin_lon: float
    dest_lat: float
    dest_lon: float


class RoutingService:
    def __init__(
        self,
        session: AsyncSession,
        base_url: str | None = None,
        user_agent: str | None = None,
    ) -> None:
        self.session = session
        settings = get_settings()
        self.base_url = (base_url or settings.OSRM_BASE_URL).rstrip("/")
        self.user_agent = user_agent or settings.USER_AGENT

    async def compute_distances(
        self,
        origin_lat: float,
        origin_lon: float,
        destinations: list[DistanceDestination],
    ) -> list[DistanceResult]:
        origin_key = (_round_coord(origin_lat), _round_coord(origin_lon))
        dest_keys = [(_round_coord(d.lat), _round_coord(d.lon)) for d in destinations]

        cached = await self._batch_cache_lookup(origin_key, dest_keys)

        results: list[DistanceResult | None] = [None] * len(destinations)
        missing_indices: list[int] = []

        for idx, (dest, key) in enumerate(zip(destinations, dest_keys, strict=True)):
            if key in cached:
                row = cached[key]
                results[idx] = DistanceResult(
                    id=dest.id,
                    road_distance_m=row.road_distance_m,
                    road_duration_s=row.road_duration_s,
                    source="cache",
                    straight_distance_km=haversine_km(origin_lat, origin_lon, dest.lat, dest.lon),
                )
            else:
                missing_indices.append(idx)

        if missing_indices:
            missing_dests = [destinations[i] for i in missing_indices]
            osrm_pairs: list[tuple[float, float] | None]
            try:
                osrm_pairs = await self._osrm_table(
                    origin_lat, origin_lon, missing_dests
                )
            except (httpx.HTTPError, ValueError) as exc:
                log.warning("osrm_failed_fallback_haversine", error=str(exc))
                osrm_pairs = [None] * len(missing_dests)

            upserts: list[tuple[float, float, int, int]] = []
            for idx, dest, pair in zip(
                missing_indices, missing_dests, osrm_pairs, strict=True
            ):
                straight = haversine_km(origin_lat, origin_lon, dest.lat, dest.lon)
                if pair is None:
                    results[idx] = DistanceResult(
                        id=dest.id,
                        road_distance_m=None,
                        road_duration_s=None,
                        source="haversine",
                        straight_distance_km=straight,
                    )
                else:
                    distance_m, duration_s = pair
                    results[idx] = DistanceResult(
                        id=dest.id,
                        road_distance_m=int(distance_m),
                        road_duration_s=int(duration_s),
                        source="osrm",
                        straight_distance_km=straight,
                    )
                    rounded_dest = (_round_coord(dest.lat), _round_coord(dest.lon))
                    upserts.append(
                        (rounded_dest[0], rounded_dest[1], int(distance_m), int(duration_s))
                    )

            if upserts:
                await self._batch_cache_upsert(origin_key, upserts)
                await self.session.commit()

        # type: ignore[return-value]
        return [r for r in results if r is not None]

    async def _batch_cache_lookup(
        self,
        origin_key: tuple[float, float],
        dest_keys: list[tuple[float, float]],
    ) -> dict[tuple[float, float], DistanceCache]:
        if not dest_keys:
            return {}
        pairs = [
            and_(
                DistanceCache.origin_lat == origin_key[0],
                DistanceCache.origin_lon == origin_key[1],
                DistanceCache.dest_lat == dlat,
                DistanceCache.dest_lon == dlon,
            )
            for dlat, dlon in dest_keys
        ]
        from sqlalchemy import or_

        rows = await self.session.execute(select(DistanceCache).where(or_(*pairs)))
        return {(row.dest_lat, row.dest_lon): row for row in rows.scalars().all()}

    async def _batch_cache_upsert(
        self,
        origin_key: tuple[float, float],
        upserts: list[tuple[float, float, int, int]],
    ) -> None:
        for dest_lat, dest_lon, dist_m, dur_s in upserts:
            stmt = (
                pg_insert(DistanceCache)
                .values(
                    origin_lat=origin_key[0],
                    origin_lon=origin_key[1],
                    dest_lat=dest_lat,
                    dest_lon=dest_lon,
                    road_distance_m=dist_m,
                    road_duration_s=dur_s,
                )
                .on_conflict_do_update(
                    index_elements=["origin_lat", "origin_lon", "dest_lat", "dest_lon"],
                    set_={
                        "road_distance_m": dist_m,
                        "road_duration_s": dur_s,
                    },
                )
            )
            await self.session.execute(stmt)

    async def _osrm_table(
        self,
        origin_lat: float,
        origin_lon: float,
        destinations: list[DistanceDestination],
    ) -> list[tuple[float, float] | None]:
        """Llama a OSRM y devuelve `[(distance_m, duration_s), ...]` o `[None, ...]`
        cuando la respuesta global no es válida."""
        if len(destinations) > OSRM_MAX_DESTINATIONS:
            # Si alguna vez excedemos, partir en chunks. Por ahora, el frontend
            # invoca distancia bajo demanda (1 destino) o batch acotado.
            raise ValueError(f"OSRM batch demasiado grande ({len(destinations)})")

        coords = [f"{origin_lon},{origin_lat}"]
        coords.extend(f"{d.lon},{d.lat}" for d in destinations)
        path = f"/table/v1/driving/{';'.join(coords)}"
        params = {
            "sources": "0",
            "destinations": ";".join(str(i + 1) for i in range(len(destinations))),
            "annotations": "distance,duration",
        }

        async with httpx.AsyncClient(
            base_url=self.base_url,
            timeout=httpx.Timeout(OSRM_TIMEOUT_S, connect=5.0),
            headers={"User-Agent": self.user_agent},
        ) as client:
            response = await client.get(path, params=params)
            response.raise_for_status()
            payload = response.json()

        if payload.get("code") != "Ok":
            raise ValueError(f"OSRM code={payload.get('code')!r}")

        durations = (payload.get("durations") or [[]])[0]
        distances = (payload.get("distances") or [[]])[0]
        if len(durations) != len(destinations) or len(distances) != len(destinations):
            raise ValueError("OSRM tamaño de matriz inesperado")

        out: list[tuple[float, float] | None] = []
        for dist, dur in zip(distances, durations, strict=True):
            if dist is None or dur is None:
                out.append(None)
            else:
                out.append((float(dist), float(dur)))
        return out
