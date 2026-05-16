from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.persistence import get_operational_store


def database_path(settings: Settings) -> str | Path:
    return get_operational_store(settings).database_path(settings)


def connect_db(settings: Settings) -> Any:
    return get_operational_store(settings).connect_db(settings)


def ensure_schema(settings: Settings) -> None:
    get_operational_store(settings).ensure_schema(settings)


def replace_sensors(settings: Settings, sensors: pd.DataFrame) -> None:
    get_operational_store(settings).replace_sensors(settings, sensors)


def replace_observations(settings: Settings, observations: pd.DataFrame) -> None:
    get_operational_store(settings).replace_observations(settings, observations)


def upsert_observations(settings: Settings, observations: pd.DataFrame) -> int:
    return get_operational_store(settings).upsert_observations(settings, observations)


def append_raw_messages(settings: Settings, rows: list[dict[str, Any]]) -> int:
    return get_operational_store(settings).append_raw_messages(settings, rows)


def replace_snapshots(settings: Settings, snapshots: pd.DataFrame) -> None:
    get_operational_store(settings).replace_snapshots(settings, snapshots)


def read_sensors(settings: Settings) -> pd.DataFrame:
    return get_operational_store(settings).read_sensors(settings)


def read_observations(settings: Settings) -> pd.DataFrame:
    return get_operational_store(settings).read_observations(settings)


def read_snapshots(settings: Settings) -> pd.DataFrame:
    return get_operational_store(settings).read_snapshots(settings)


def read_snapshot_timestamps(settings: Settings, pollutant: str) -> list[str]:
    return get_operational_store(settings).read_snapshot_timestamps(settings, pollutant)


def read_snapshot(settings: Settings, pollutant: str, timestamp: str | pd.Timestamp) -> pd.DataFrame:
    return get_operational_store(settings).read_snapshot(settings, pollutant, timestamp)


def read_sensor_snapshot(settings: Settings, sensor_id: str, timestamp: str | pd.Timestamp) -> pd.DataFrame:
    return get_operational_store(settings).read_sensor_snapshot(settings, sensor_id, timestamp)


def read_recent_observations(settings: Settings, since_timestamp: str | None = None) -> pd.DataFrame:
    return get_operational_store(settings).read_recent_observations(settings, since_timestamp)


def read_sensor_observations(settings: Settings, sensor_id: str) -> pd.DataFrame:
    return get_operational_store(settings).read_sensor_observations(settings, sensor_id)


def read_sensor_timeseries(settings: Settings, pollutant: str, sensor_name: str) -> pd.DataFrame:
    return get_operational_store(settings).read_sensor_timeseries(settings, pollutant, sensor_name)


def read_raw_messages(settings: Settings) -> pd.DataFrame:
    return get_operational_store(settings).read_raw_messages(settings)


def read_raw_message_count(settings: Settings) -> int:
    return get_operational_store(settings).read_raw_message_count(settings)


def upsert_job_run(settings: Settings, job: dict[str, Any]) -> None:
    get_operational_store(settings).upsert_job_run(settings, job)


def read_job_run(settings: Settings, job_id: str) -> dict[str, Any] | None:
    return get_operational_store(settings).read_job_run(settings, job_id)


def read_job_runs(settings: Settings, limit: int = 20) -> list[dict[str, Any]]:
    return get_operational_store(settings).read_job_runs(settings, limit)


def write_ingestion_run(settings: Settings, metadata: dict[str, Any], status: str = "completed") -> None:
    get_operational_store(settings).write_ingestion_run(settings, metadata, status=status)


def write_metadata(settings: Settings, key: str, value: Any) -> None:
    get_operational_store(settings).write_metadata(settings, key, value)


def read_metadata(settings: Settings) -> dict[str, Any]:
    return get_operational_store(settings).read_metadata(settings)


def append_operational_event(
    settings: Settings,
    event_type: str,
    payload: dict[str, Any],
    *,
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    occurred_at: str | None = None,
) -> int:
    return get_operational_store(settings).append_operational_event(
        settings,
        event_type,
        payload,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        occurred_at=occurred_at,
    )


def read_operational_events(
    settings: Settings,
    *,
    after_event_id: int = 0,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return get_operational_store(settings).read_operational_events(
        settings,
        after_event_id=after_event_id,
        limit=limit,
    )


def read_latest_event_id(settings: Settings) -> int:
    return get_operational_store(settings).read_latest_event_id(settings)


def upsert_projection_failure(settings: Settings, failure: dict[str, Any]) -> None:
    get_operational_store(settings).upsert_projection_failure(settings, failure)


def read_projection_failure(settings: Settings, event_id: int) -> dict[str, Any] | None:
    return get_operational_store(settings).read_projection_failure(settings, event_id)


def delete_projection_failure(settings: Settings, event_id: int) -> None:
    get_operational_store(settings).delete_projection_failure(settings, event_id)


def read_projection_failures(
    settings: Settings,
    *,
    status: str | None = None,
    limit: int = 100,
) -> list[dict[str, Any]]:
    return get_operational_store(settings).read_projection_failures(settings, status=status, limit=limit)


def read_projection_failure_summary(settings: Settings) -> dict[str, Any]:
    return get_operational_store(settings).read_projection_failure_summary(settings)
