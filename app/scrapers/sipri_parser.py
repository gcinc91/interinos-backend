"""Parser de la respuesta GeoJSON de SIPRI a `VacancyDTO`s.

SIPRI devuelve `FeatureCollection` con properties:
  Centro, Tipo, Fecha, Participación, Observaciones, Puesto, Localidad, Provincia
y geometry Point [lon, lat] EPSG:4326.

Convenciones:
- `Centro` y `Puesto` vienen como `"<código> - <nombre>"`.
- `cuerpo` se infiere por el primer match `\\d{3}` dentro del código del puesto.
- `Fecha` puede ser "Sin determinar" o `dd/mm/yyyy`.
- `source_id` y `content_hash` son sha256 truncados (estables entre runs).
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime
from typing import Any

from app.scrapers.dto import VacancyDTO

CUERPO_LOOKAHEAD = re.compile(r"(?=(\d{3}))")
KNOWN_CUERPOS = {"590", "591", "592", "593", "594", "595", "596", "597", "598"}
FECHA_FORMAT = "%d/%m/%Y"
SIN_DETERMINAR = {"sin determinar", "sin determinar.", ""}


def _split_codigo_nombre(value: str | None) -> tuple[str | None, str | None]:
    """`"00590018 - ORIENTACION..." -> ("00590018", "ORIENTACION...")`."""
    if not value:
        return None, None
    parts = value.split(" - ", 1)
    if len(parts) == 2:
        return parts[0].strip() or None, parts[1].strip() or None
    return None, value.strip() or None


def _derive_cuerpo(puesto_codigo: str | None) -> str:
    """Extrae el cuerpo (590, 597, ...) buscando dentro del código de puesto.

    SIPRI codifica el código como `<padding><cuerpo><especialidad>`, p.ej.
    `00590018` → cuerpo 590. Letras prefijo (`ZT`, `MA`, `EN`...) son posibles.
    Buscamos overlapping 3-grams numéricos y devolvemos el primero que coincida
    con la lista de cuerpos docentes conocidos. Fallback: 'OTROS'.
    """
    if not puesto_codigo:
        return "OTROS"
    for candidate in CUERPO_LOOKAHEAD.findall(puesto_codigo):
        if candidate in KNOWN_CUERPOS:
            return candidate
    return "OTROS"


def _parse_fecha(raw: str | None) -> datetime | None:
    if not raw:
        return None
    cleaned = raw.strip()
    if cleaned.lower().rstrip(".") in {s.rstrip(".") for s in SIN_DETERMINAR}:
        return None
    try:
        return datetime.strptime(cleaned, FECHA_FORMAT)
    except ValueError:
        return None


def _stable_hash(parts: list[str | None]) -> str:
    payload = "|".join("" if p is None else str(p) for p in parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _content_hash(raw_payload: dict[str, Any]) -> str:
    canonical = json.dumps(raw_payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def parse_feature(feature: dict[str, Any]) -> VacancyDTO:
    props = feature.get("properties", {}) or {}
    geometry = feature.get("geometry", {}) or {}
    coords = geometry.get("coordinates") or [None, None]
    lon, lat = (coords + [None, None])[:2]
    if lat is None or lon is None:
        raise ValueError(f"Feature sin coordenadas válidas: {feature.get('id')}")

    centro_codigo, centro = _split_codigo_nombre(props.get("Centro"))
    puesto_codigo, especialidad = _split_codigo_nombre(props.get("Puesto"))
    cuerpo = _derive_cuerpo(puesto_codigo)
    fecha_cese = _parse_fecha(props.get("Fecha"))

    tipo = (props.get("Tipo") or "").strip() or None
    participacion = (props.get("Participación") or "").strip() or None
    localidad = (props.get("Localidad") or "").strip() or None
    provincia = (props.get("Provincia") or "").strip() or None
    observaciones_raw = props.get("Observaciones")
    observaciones = observaciones_raw.strip() if isinstance(observaciones_raw, str) else None

    if centro is None:
        raise ValueError(f"Feature sin Centro: {feature.get('id')}")

    source_id = _stable_hash(
        [centro_codigo, puesto_codigo, tipo, participacion, localidad, observaciones]
    )

    raw_payload = {
        "properties": props,
        "geometry": geometry,
    }
    content_hash = _content_hash(raw_payload)

    return VacancyDTO(
        source_id=source_id,
        cuerpo=cuerpo,
        especialidad=especialidad,
        centro=centro,
        centro_codigo=centro_codigo,
        puesto_codigo=puesto_codigo,
        localidad=localidad,
        provincia=provincia,
        tipo=tipo,
        participacion=participacion,
        observaciones=observaciones,
        fecha_cese=fecha_cese,
        lat=float(lat),
        lon=float(lon),
        raw_payload=raw_payload,
        content_hash=content_hash,
    )


def parse_feature_collection(geojson: dict[str, Any]) -> list[VacancyDTO]:
    features = geojson.get("features") or []
    out: list[VacancyDTO] = []
    seen: set[str] = set()
    for feat in features:
        try:
            dto = parse_feature(feat)
        except ValueError:
            continue  # skip features rotas
        if dto.source_id in seen:
            continue
        seen.add(dto.source_id)
        out.append(dto)
    return out
