from unittest.mock import AsyncMock, MagicMock

from pytest_httpx import HTTPXMock

from app.services.geocode_service import (
    NominatimClient,
    GeocodeService,
    normalize_address,
)


# --- normalize_address ----------------------------------------------------


def test_normalize_lowercases_and_collapses_whitespace() -> None:
    assert normalize_address("  Calle  Sierpes 7,  Sevilla  ") == (
        "calle sierpes 7, sevilla, andalucía, españa"
    )


def test_normalize_appends_andalucia_when_missing() -> None:
    assert normalize_address("Sevilla") == "sevilla, andalucía, españa"


def test_normalize_does_not_double_append() -> None:
    addr = "Granada, Andalucía, España"
    assert normalize_address(addr) == "granada, andalucía, españa"


def test_normalize_skips_when_spain_present() -> None:
    assert normalize_address("Cádiz, España") == "cádiz, españa"


# --- NominatimClient ------------------------------------------------------


async def test_nominatim_returns_coords(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json=[{"lat": "37.3886", "lon": "-5.9823"}])
    client = NominatimClient(base_url="https://nominatim.test", user_agent="UA/1")
    result = await client.search("sevilla")
    assert result == (37.3886, -5.9823)


async def test_nominatim_returns_none_on_empty(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json=[])
    client = NominatimClient(base_url="https://nominatim.test", user_agent="UA/1")
    assert await client.search("xxx-no-such-place") is None


async def test_nominatim_sends_user_agent(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json=[{"lat": "37.0", "lon": "-5.0"}])
    client = NominatimClient(base_url="https://nominatim.test", user_agent="MyBot/9.9")
    await client.search("sevilla")
    request = httpx_mock.get_request()
    assert request is not None
    assert request.headers["user-agent"] == "MyBot/9.9"


# --- GeocodeService -------------------------------------------------------


def _stub_session_with_cached_row(lat: float, lon: float) -> AsyncMock:
    cached_row = MagicMock(lat=lat, lon=lon)
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=cached_row)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=select_result)
    session.commit = AsyncMock()
    return session


def _stub_session_with_no_cache() -> AsyncMock:
    select_result = MagicMock()
    select_result.scalar_one_or_none = MagicMock(return_value=None)
    session = AsyncMock()
    session.execute = AsyncMock(return_value=select_result)
    session.commit = AsyncMock()
    return session


async def test_geocode_cache_hit_does_not_call_upstream(httpx_mock: HTTPXMock) -> None:
    """Si hay cache, no debe hacerse ninguna petición a Nominatim."""
    session = _stub_session_with_cached_row(lat=37.4, lon=-5.99)
    nominatim = NominatimClient(base_url="https://nominatim.test", user_agent="UA")
    service = GeocodeService(session=session, nominatim=nominatim)

    result = await service.geocode("Sevilla")

    assert result is not None
    lat, lon, norm, cached = result
    assert (lat, lon) == (37.4, -5.99)
    assert cached is True
    assert norm == "sevilla, andalucía, españa"
    # Solo el SELECT — sin INSERT, sin commit, sin HTTP
    assert session.execute.await_count == 1
    session.commit.assert_not_awaited()
    # pytest-httpx falla si quedan respuestas mockeadas no usadas → asegura no hubo HTTP
    assert httpx_mock.get_requests() == []


async def test_geocode_cache_miss_calls_nominatim_and_upserts(
    httpx_mock: HTTPXMock,
) -> None:
    httpx_mock.add_response(json=[{"lat": "36.7213", "lon": "-4.4214"}])
    session = _stub_session_with_no_cache()
    nominatim = NominatimClient(base_url="https://nominatim.test", user_agent="UA")
    service = GeocodeService(session=session, nominatim=nominatim)

    result = await service.geocode("Málaga")

    assert result is not None
    lat, lon, _, cached = result
    assert (lat, lon) == (36.7213, -4.4214)
    assert cached is False
    # SELECT + INSERT
    assert session.execute.await_count == 2
    session.commit.assert_awaited_once()


async def test_geocode_returns_none_when_nominatim_empty(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(json=[])
    session = _stub_session_with_no_cache()
    nominatim = NominatimClient(base_url="https://nominatim.test", user_agent="UA")
    service = GeocodeService(session=session, nominatim=nominatim)

    assert await service.geocode("xxxx") is None
    # Sin upsert ni commit
    assert session.execute.await_count == 1
    session.commit.assert_not_awaited()
