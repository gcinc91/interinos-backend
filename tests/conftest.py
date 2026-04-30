import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture(scope="session")
def sipri_fixture() -> dict[str, Any]:
    path = FIXTURES_DIR / "sipri" / "sipri-buscarjson-sample.json"
    return json.loads(path.read_text(encoding="utf-8"))
