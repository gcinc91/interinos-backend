"""Smoke test que golpea SIPRI real.

Saltado por defecto. Para correrlo: `uv run pytest -m live`.
"""
import pytest

from app.scrapers.sipri_client import SipriClient
from app.scrapers.sipri_parser import parse_feature_collection

pytestmark = pytest.mark.live


async def test_fetch_real_sipri_returns_geojson() -> None:
    client = SipriClient()
    payload = await client.fetch_geojson()
    assert payload["type"] == "FeatureCollection"
    features = payload.get("features", [])
    assert len(features) > 0


async def test_parse_real_sipri_yields_dtos() -> None:
    client = SipriClient()
    payload = await client.fetch_geojson()
    dtos = parse_feature_collection(payload)
    assert len(dtos) > 0
    # Sanidad: la mayoría deben caer en cuerpos docentes conocidos
    known = sum(1 for d in dtos if d.cuerpo != "OTROS")
    assert known / len(dtos) > 0.9
