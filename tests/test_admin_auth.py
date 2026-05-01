import pytest
from fastapi import HTTPException

from app.api.admin import require_admin_token
from app.core.config import get_settings


@pytest.fixture(autouse=True)
def _clear_settings_cache() -> None:
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_no_token_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        require_admin_token(None)
    assert exc.value.status_code == 401


def test_empty_token_raises_401() -> None:
    with pytest.raises(HTTPException) as exc:
        require_admin_token("")
    assert exc.value.status_code == 401


def test_default_change_me_always_rejects(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "change-me")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        require_admin_token("change-me")
    assert exc.value.status_code == 401


def test_wrong_token_raises_401(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "supersecret")
    get_settings.cache_clear()
    with pytest.raises(HTTPException) as exc:
        require_admin_token("not-the-token")
    assert exc.value.status_code == 401


def test_correct_token_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ADMIN_TOKEN", "supersecret")
    get_settings.cache_clear()
    require_admin_token("supersecret")  # no debe lanzar
