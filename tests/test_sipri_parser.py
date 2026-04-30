from datetime import datetime

import pytest

from app.scrapers.sipri_parser import (
    _derive_cuerpo,
    _parse_fecha,
    _split_codigo_nombre,
    parse_feature,
    parse_feature_collection,
)


def test_split_codigo_nombre_normal() -> None:
    assert _split_codigo_nombre("00590018 - ORIENTACIÓN EDUCATIVA P.E.S.") == (
        "00590018",
        "ORIENTACIÓN EDUCATIVA P.E.S.",
    )


def test_split_codigo_nombre_none_or_empty() -> None:
    assert _split_codigo_nombre(None) == (None, None)
    assert _split_codigo_nombre("") == (None, None)


def test_split_codigo_nombre_no_dash() -> None:
    assert _split_codigo_nombre("SOLO_NOMBRE") == (None, "SOLO_NOMBRE")


def test_derive_cuerpo_standard_codes() -> None:
    assert _derive_cuerpo("00590018") == "590"
    assert _derive_cuerpo("00597031") == "597"


def test_derive_cuerpo_with_prefix() -> None:
    assert _derive_cuerpo("ZT597038") == "597"
    assert _derive_cuerpo("MA590109") == "590"


def test_derive_cuerpo_unknown_returns_otros() -> None:
    # `EN3DJ229` no contiene un cuerpo docente conocido (5xx) → OTROS
    assert _derive_cuerpo("EN3DJ229") == "OTROS"


def test_derive_cuerpo_fallback() -> None:
    assert _derive_cuerpo(None) == "OTROS"
    assert _derive_cuerpo("AB") == "OTROS"


def test_parse_fecha_real_date() -> None:
    assert _parse_fecha("19/05/2026") == datetime(2026, 5, 19)


def test_parse_fecha_sin_determinar() -> None:
    assert _parse_fecha("Sin determinar") is None
    assert _parse_fecha("sin determinar.") is None


def test_parse_fecha_invalid_returns_none() -> None:
    assert _parse_fecha("foo") is None
    assert _parse_fecha(None) is None


def test_parse_feature_real() -> None:
    feature = {
        "type": "Feature",
        "id": "1",
        "properties": {
            "Centro": "14007350 - I.E.S. Ingeniero Juan de la Cierva",
            "Tipo": "Sustitución",
            "Fecha": "19/05/2026",
            "Participación": "Obligatoria",
            "Observaciones": "  CENTRO VOLUNTARIO.  ",
            "Puesto": "00590018 - ORIENTACIÓN EDUCATIVA P.E.S.",
            "Localidad": "Puente Genil",
            "Provincia": "Córdoba",
        },
        "geometry": {"type": "Point", "coordinates": [-4.768, 37.383]},
    }
    dto = parse_feature(feature)
    assert dto.cuerpo == "590"
    assert dto.especialidad == "ORIENTACIÓN EDUCATIVA P.E.S."
    assert dto.centro == "I.E.S. Ingeniero Juan de la Cierva"
    assert dto.centro_codigo == "14007350"
    assert dto.puesto_codigo == "00590018"
    assert dto.tipo == "Sustitución"
    assert dto.participacion == "Obligatoria"
    assert dto.observaciones == "CENTRO VOLUNTARIO."
    assert dto.localidad == "Puente Genil"
    assert dto.provincia == "Córdoba"
    assert dto.fecha_cese == datetime(2026, 5, 19)
    assert dto.lat == 37.383
    assert dto.lon == -4.768
    assert len(dto.source_id) == 32
    assert len(dto.content_hash) == 32


def test_parse_feature_handles_null_observaciones() -> None:
    feature = {
        "properties": {
            "Centro": "X - Y",
            "Tipo": "Vacante",
            "Fecha": "Sin determinar",
            "Participación": "Voluntaria",
            "Observaciones": None,
            "Puesto": "00597031 - EDUCACIÓN INFANTIL",
            "Localidad": "Armilla",
            "Provincia": "Granada",
        },
        "geometry": {"type": "Point", "coordinates": [-3.6, 37.1]},
    }
    dto = parse_feature(feature)
    assert dto.observaciones is None
    assert dto.fecha_cese is None


def test_parse_feature_rejects_missing_coords() -> None:
    feature = {
        "properties": {"Centro": "X - Y", "Puesto": "00590001 - X"},
        "geometry": {"type": "Point", "coordinates": []},
    }
    with pytest.raises(ValueError):
        parse_feature(feature)


def test_source_id_stable_across_runs() -> None:
    feature = {
        "properties": {
            "Centro": "C - n",
            "Tipo": "Sustitución",
            "Fecha": "Sin determinar",
            "Participación": "Obligatoria",
            "Observaciones": None,
            "Puesto": "00590001 - X",
            "Localidad": "L",
            "Provincia": "P",
        },
        "geometry": {"type": "Point", "coordinates": [0.0, 0.0]},
    }
    a = parse_feature(feature)
    b = parse_feature(feature)
    assert a.source_id == b.source_id
    assert a.content_hash == b.content_hash


def test_source_id_changes_with_relevant_field() -> None:
    base_props = {
        "Centro": "C - n",
        "Tipo": "Sustitución",
        "Fecha": "Sin determinar",
        "Participación": "Obligatoria",
        "Observaciones": None,
        "Puesto": "00590001 - X",
        "Localidad": "L1",
        "Provincia": "P",
    }
    other_props = {**base_props, "Localidad": "L2"}
    a = parse_feature({"properties": base_props, "geometry": {"coordinates": [0, 0]}})
    b = parse_feature({"properties": other_props, "geometry": {"coordinates": [0, 0]}})
    assert a.source_id != b.source_id


def test_parse_collection_full_fixture(sipri_fixture: dict) -> None:
    dtos = parse_feature_collection(sipri_fixture)
    assert len(dtos) > 0
    # esperamos que la mayoría de las 298 features se parseen sin colapsar
    assert len(dtos) >= 280
    # Cuerpos típicos presentes
    cuerpos = {dto.cuerpo for dto in dtos}
    assert {"590", "597"}.issubset(cuerpos)
    # Provincias andaluzas
    provincias = {dto.provincia for dto in dtos}
    assert "Sevilla" in provincias and "Córdoba" in provincias
    # Coordenadas dentro de un bounding box laxo de Andalucía
    for dto in dtos:
        assert -8.0 < dto.lon < -1.0
        assert 35.0 < dto.lat < 39.0


def test_parse_collection_idempotent(sipri_fixture: dict) -> None:
    a = parse_feature_collection(sipri_fixture)
    b = parse_feature_collection(sipri_fixture)
    assert [d.source_id for d in a] == [d.source_id for d in b]
    assert [d.content_hash for d in a] == [d.content_hash for d in b]
