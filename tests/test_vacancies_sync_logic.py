"""Unit tests para la lógica pura de sincronización (sin DB)."""
from app.scrapers.dto import VacancyDTO
from app.services.vacancies_sync import compute_data_version, compute_diff


def _dto(source_id: str, content_hash: str = "h", lat: float = 37.0, lon: float = -5.0) -> VacancyDTO:
    return VacancyDTO(
        source_id=source_id,
        cuerpo="590",
        especialidad="X",
        centro="C",
        centro_codigo="C1",
        puesto_codigo="00590001",
        localidad="L",
        provincia="Sevilla",
        tipo="Sustitución",
        participacion="Obligatoria",
        observaciones=None,
        fecha_cese=None,
        lat=lat,
        lon=lon,
        raw_payload={"properties": {"x": 1}},
        content_hash=content_hash,
    )


# --- compute_data_version --------------------------------------------------


def test_data_version_stable_for_same_set() -> None:
    a = [_dto("s1", "h1"), _dto("s2", "h2")]
    b = [_dto("s2", "h2"), _dto("s1", "h1")]  # mismo set, distinto orden
    assert compute_data_version(a) == compute_data_version(b)


def test_data_version_changes_on_content_hash_change() -> None:
    a = [_dto("s1", "h1")]
    b = [_dto("s1", "h2")]
    assert compute_data_version(a) != compute_data_version(b)


def test_data_version_changes_on_membership_change() -> None:
    a = [_dto("s1", "h1")]
    b = [_dto("s1", "h1"), _dto("s2", "h2")]
    assert compute_data_version(a) != compute_data_version(b)


def test_data_version_empty_is_deterministic() -> None:
    assert compute_data_version([]) == compute_data_version([])
    assert len(compute_data_version([])) == 32


# --- compute_diff ----------------------------------------------------------


def test_diff_first_run_all_new() -> None:
    incoming = [_dto("s1", "h1"), _dto("s2", "h2")]
    diff = compute_diff(existing={}, incoming=incoming)
    assert [d.source_id for d in diff.new] == ["s1", "s2"]
    assert diff.updated == []
    assert diff.unchanged == []
    assert diff.removed_source_ids == []


def test_diff_idempotent_run_all_unchanged() -> None:
    incoming = [_dto("s1", "h1"), _dto("s2", "h2")]
    existing = {"s1": ("h1", True), "s2": ("h2", True)}
    diff = compute_diff(existing, incoming)
    assert diff.new == []
    assert diff.updated == []
    assert {d.source_id for d in diff.unchanged} == {"s1", "s2"}
    assert diff.removed_source_ids == []


def test_diff_content_hash_change_marks_updated() -> None:
    existing = {"s1": ("oldhash", True)}
    incoming = [_dto("s1", "newhash")]
    diff = compute_diff(existing, incoming)
    assert diff.updated and diff.updated[0].source_id == "s1"
    assert diff.new == []
    assert diff.unchanged == []


def test_diff_inactive_existing_resurrected_as_updated() -> None:
    """Si en BD hay s1 inactivo y aparece otra vez en SIPRI, lo tratamos como
    update (lo reactivamos), no como new."""
    existing = {"s1": ("h1", False)}
    incoming = [_dto("s1", "h1")]
    diff = compute_diff(existing, incoming)
    assert diff.updated and diff.updated[0].source_id == "s1"
    assert diff.unchanged == []


def test_diff_removed_source_ids_only_count_active() -> None:
    existing = {
        "s1": ("h1", True),  # activo y se va → remove
        "s2": ("h2", False),  # ya inactivo → no contar
    }
    incoming: list[VacancyDTO] = []
    diff = compute_diff(existing, incoming)
    assert diff.removed_source_ids == ["s1"]


def test_diff_combined_scenario() -> None:
    existing = {
        "keep": ("h-keep", True),
        "modify": ("h-old", True),
        "gone": ("h-gone", True),
    }
    incoming = [
        _dto("keep", "h-keep"),
        _dto("modify", "h-new"),
        _dto("brand-new", "h-bn"),
    ]
    diff = compute_diff(existing, incoming)
    assert {d.source_id for d in diff.unchanged} == {"keep"}
    assert {d.source_id for d in diff.updated} == {"modify"}
    assert {d.source_id for d in diff.new} == {"brand-new"}
    assert diff.removed_source_ids == ["gone"]
