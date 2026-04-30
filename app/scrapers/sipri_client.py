"""Cliente HTTP de SIPRI (Sistema de Provisión de Interinidades, Junta de Andalucía).

Estrategia:
1. GET `/sipri/plazas/plaza` para obtener la cookie `JSESSIONID`.
2. POST `/sipri/plazas/buscarjson` con `pos=0` y filtros vacíos. Devuelve un
   `FeatureCollection` GeoJSON (EPSG:4326) con todas las plazas activas.

Sin autenticación de usuario: la sesión es anónima.
"""
from __future__ import annotations

from typing import Any

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.config import get_settings
from app.core.logging import get_logger

log = get_logger(__name__)


class SipriClient:
    PLAZA_PATH = "/sipri/plazas/plaza"
    BUSCAR_JSON_PATH = "/sipri/plazas/buscarjson"

    def __init__(self, base_url: str | None = None, user_agent: str | None = None) -> None:
        settings = get_settings()
        self._base_url = (base_url or settings.SIPRI_BASE_URL).rstrip("/")
        self._user_agent = user_agent or settings.USER_AGENT

    def _build_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(30.0, connect=10.0),
            headers={
                "User-Agent": self._user_agent,
                "Accept-Language": "es-ES,es;q=0.9",
            },
            follow_redirects=True,
        )

    async def fetch_geojson(
        self,
        *,
        pos: int = 0,
        cuerpo: str = "",
        puesto: str = "",
        provincia: str = "",
        municipio: str = "",
        localidad: str = "",
        participacion: str = "",
        tipo: str = "",
    ) -> dict[str, Any]:
        """Obtiene el `FeatureCollection` GeoJSON de plazas SIPRI. Reintenta con backoff."""
        async for attempt in AsyncRetrying(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=2, max=30),
            retry=retry_if_exception_type((httpx.HTTPError, ValueError)),
            reraise=True,
        ):
            with attempt:
                async with self._build_client() as client:
                    log.info("sipri_init_session", base_url=self._base_url)
                    init_response = await client.get(self.PLAZA_PATH)
                    init_response.raise_for_status()

                    log.info("sipri_buscarjson", pos=pos)
                    response = await client.post(
                        self.BUSCAR_JSON_PATH,
                        data={
                            "pos": str(pos),
                            "cuerpo": cuerpo,
                            "puesto": puesto,
                            "provincia": provincia,
                            "municipio": municipio,
                            "localidad": localidad,
                            "participacion": participacion,
                            "tipo": tipo,
                        },
                        headers={
                            "X-Requested-With": "XMLHttpRequest",
                            "Referer": f"{self._base_url}{self.PLAZA_PATH}",
                        },
                    )
                    response.raise_for_status()
                    content_type = response.headers.get("content-type", "")
                    if "json" not in content_type.lower():
                        raise ValueError(
                            f"Respuesta no-JSON de SIPRI (content-type={content_type!r}). "
                            "Probable expiración de cookie."
                        )
                    payload: dict[str, Any] = response.json()
                    if payload.get("type") != "FeatureCollection":
                        raise ValueError(f"GeoJSON inesperado: type={payload.get('type')!r}")
                    log.info(
                        "sipri_response_ok", features=len(payload.get("features", []))
                    )
                    return payload
        raise RuntimeError("unreachable")
