from unittest.mock import AsyncMock, MagicMock

import httpx
from pytest_httpx import HTTPXMock

from app.schemas.distance import DistanceDestination
from app.services.routing_service import RoutingService, haversine_km


# --- haversine pure -------------------------------------------------------


def test_haversine_zero_for_same_point() -> None:
    assert haversine_km(37.0, -5.0, 37.0, -5.0) == 0.0


def test_haversine_sevilla_to_malaga_approx() -> None:
    # Centros aproximados: Sevilla 37.388,-5.995  Málaga 36.721,-4.421
    km = haversine_km(37.388, -5.995, 36.721, -4.421)
    # Distancia recta esperada ~157 km
    assert 150 < km < 165


def test_haversine_symmetric() -> None:
    a = haversine_km(37.0, -5.0, 36.0, -4.0)
    b = haversine_km(36.0, -4.0, 37.0, -5.0)
    assert abs(a - b) < 1e-9


# --- RoutingService -------------------------------------------------------


def _stub_session_with_no_cache() -> AsyncMock:
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = []
    session = AsyncMock()
    session.execute = AsyncMock(return_value=select_result)
    session.commit = AsyncMock()
    return session


def _stub_session_with_cached_pair(
    dest_lat: float, dest_lon: float, dist_m: int, dur_s: int
) -> AsyncMock:
    cached = MagicMock(
        dest_lat=dest_lat,
        dest_lon=dest_lon,
        road_distance_m=dist_m,
        road_duration_s=dur_s,
    )
    select_result = MagicMock()
    select_result.scalars.return_value.all.return_value = [cached]
    session = AsyncMock()
    session.execute = AsyncMock(return_value=select_result)
    session.commit = AsyncMock()
    return session


async def test_cache_hit_does_not_call_osrm(httpx_mock: HTTPXMock) -> None:
    """Si todos los destinos están en cache, no se llama a OSRM."""
    dest_lat, dest_lon = 36.72130, -4.42140
    session = _stub_session_with_cached_pair(dest_lat, dest_lon, 200000, 9000)
    service = RoutingService(session=session, base_url="https://osrm.test", user_agent="UA")

    results = await service.compute_distances(
        origin_lat=37.388,
        origin_lon=-5.995,
        destinations=[DistanceDestination(id=1, lat=dest_lat, lon=dest_lon)],
    )
    assert len(results) == 1
    assert results[0].source == "cache"
    assert results[0].road_distance_m == 200000
    assert results[0].road_duration_s == 9000
    assert results[0].straight_distance_km > 0
    assert httpx_mock.get_requests() == []
    session.commit.assert_not_awaited()


async def test_cache_miss_calls_osrm_and_upserts(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        json={
            "code": "Ok",
            "durations": [[9000.0]],
            "distances": [[200000.0]],
        }
    )
    session = _stub_session_with_no_cache()
    service = RoutingService(session=session, base_url="https://osrm.test", user_agent="UA")

    results = await service.compute_distances(
        origin_lat=37.388,
        origin_lon=-5.995,
        destinations=[DistanceDestination(id="a", lat=36.721, lon=-4.421)],
    )
    assert len(results) == 1
    assert results[0].source == "osrm"
    assert results[0].road_distance_m == 200000
    assert results[0].road_duration_s == 9000
    # SELECT (cache lookup) + INSERT (upsert) = al menos 2 awaits a session.execute
    assert session.execute.await_count >= 2
    session.commit.assert_awaited_once()


async def test_osrm_error_falls_back_to_haversine(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_exception(httpx.ConnectError("boom"))
    session = _stub_session_with_no_cache()
    service = RoutingService(session=session, base_url="https://osrm.test", user_agent="UA")

    results = await service.compute_distances(
        origin_lat=37.388,
        origin_lon=-5.995,
        destinations=[DistanceDestination(id=1, lat=36.721, lon=-4.421)],
    )
    assert len(results) == 1
    assert results[0].source == "haversine"
    assert results[0].road_distance_m is None
    assert results[0].road_duration_s is None
    assert results[0].straight_distance_km > 100  # ~157 km
    # Sin upsert porque OSRM falló
    session.commit.assert_not_awaited()


async def test_osrm_non_ok_code_falls_back(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json={"code": "NoRoute"})
    session = _stub_session_with_no_cache()
    service = RoutingService(session=session, base_url="https://osrm.test", user_agent="UA")

    results = await service.compute_distances(
        origin_lat=37.388,
        origin_lon=-5.995,
        destinations=[DistanceDestination(id=1, lat=36.721, lon=-4.421)],
    )
    assert results[0].source == "haversine"
