from __future__ import annotations

import os
from functools import lru_cache

from unisa_air_twin.config import Settings
from unisa_air_twin.persistence.base import OperationalStore
from unisa_air_twin.persistence.postgres_store import PostgresOperationalStore
from unisa_air_twin.persistence.sqlite_store import SQLiteOperationalStore


def resolve_backend_name(settings: Settings) -> str:
    config = settings.live_sensors.get("operational", {})
    backend = str(
        config.get("backend")
        or os.environ.get("UNISA_AQDT_PERSISTENCE_BACKEND")
        or "sqlite"
    ).strip().lower()
    if backend not in {"sqlite", "postgres"}:
        raise ValueError(f"Unsupported persistence backend: {backend}")
    return backend


@lru_cache(maxsize=2)
def _store_for_backend(backend: str) -> OperationalStore:
    if backend == "sqlite":
        return SQLiteOperationalStore()
    if backend == "postgres":
        return PostgresOperationalStore()
    raise ValueError(f"Unsupported persistence backend: {backend}")


def get_operational_store(settings: Settings) -> OperationalStore:
    return _store_for_backend(resolve_backend_name(settings))
