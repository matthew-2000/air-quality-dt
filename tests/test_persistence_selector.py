from __future__ import annotations

import pytest

from unisa_air_twin.config import load_settings
from unisa_air_twin.persistence import get_operational_store, resolve_backend_name


def test_persistence_selector_defaults_to_sqlite() -> None:
    settings = load_settings()
    settings.live_sensors["operational"] = {}

    assert resolve_backend_name(settings) == "sqlite"
    assert get_operational_store(settings).backend_name() == "sqlite"


def test_persistence_selector_rejects_unknown_backend() -> None:
    settings = load_settings()
    settings.live_sensors["operational"] = {"backend": "oracle"}

    with pytest.raises(ValueError, match="Unsupported persistence backend"):
        resolve_backend_name(settings)
