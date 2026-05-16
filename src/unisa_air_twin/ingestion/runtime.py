from __future__ import annotations

from pathlib import Path

from unisa_air_twin.config import Settings
from unisa_air_twin.utils import project_path


def snapshot_settings(settings: Settings) -> tuple[int, int]:
    config = settings.live_sensors.get("snapshots", {})
    bucket_minutes = max(1, int(config.get("bucket_minutes", 1)))
    freshness_minutes = max(bucket_minutes, int(config.get("freshness_minutes", 5)))
    return bucket_minutes, freshness_minutes


def timestamp_guard_settings(settings: Settings) -> int:
    config = settings.live_sensors.get("timestamps", {})
    return max(0, int(config.get("max_future_skew_seconds", 120)))


def configured_path(settings: Settings, key: str) -> Path:
    raw_config = settings.live_sensors.get("raw", {})
    value = raw_config.get(key)
    if not value:
        return settings.raw_dir / "live_sensors" / key.replace("_path", "")
    path = Path(value)
    return path if path.is_absolute() else project_path(path)
