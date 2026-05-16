from __future__ import annotations

import json
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.event_log import publish_operational_event
from unisa_air_twin.external_sources import read_source_statuses
from unisa_air_twin.ingestion.catalog import write_real_sensor_geojson
from unisa_air_twin.ingestion.runtime import snapshot_settings
from unisa_air_twin.ingestion.snapshots import build_operational_snapshots
from unisa_air_twin.operational_store import (
    read_latest_event_id,
    read_metadata,
    read_observations,
    read_operational_events,
    read_raw_message_count,
    read_snapshots,
    replace_observations,
    replace_sensors,
    replace_snapshots,
    upsert_observations,
    write_ingestion_run,
    write_metadata,
)
from unisa_air_twin.realtime import publish_realtime_notification
from unisa_air_twin.shared.constants import OBSERVATION_COLUMNS, SOURCE_NAME, SOURCE_URL
from unisa_air_twin.storage import write_table
from unisa_air_twin.utils import ensure_dir, utc_now_iso

OBSERVATION_CURSOR_KEY = "projection_cursor.observations"


def _frame_event_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    copy = frame.copy()
    for column in copy.columns:
        series = copy[column]
        if pd.api.types.is_datetime64_any_dtype(series):
            copy[column] = pd.to_datetime(series, errors="coerce").dt.strftime("%Y-%m-%dT%H:%M:%S")
    copy = copy.where(pd.notna(copy), None)
    return copy.to_dict(orient="records")


def _observation_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    if not records:
        return pd.DataFrame(columns=OBSERVATION_COLUMNS)
    frame = pd.DataFrame(records)
    for column in ["timestamp", "received_at", "downloaded_at"]:
        if column in frame.columns:
            frame[column] = pd.to_datetime(frame[column], errors="coerce")
    return frame


def _export_metadata(
    settings: Settings,
    observations: pd.DataFrame,
    snapshots: pd.DataFrame,
    sensors: pd.DataFrame,
    raw_message_rows: int,
) -> dict[str, object]:
    bucket_minutes, freshness_minutes = snapshot_settings(settings)
    return {
        "raw_message_rows": int(raw_message_rows),
        "observation_rows": int(len(observations)),
        "raw_rows": int(len(observations)),
        "snapshot_rows": int(len(snapshots)),
        "sensors": int(len(sensors)),
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "generated_at": utc_now_iso(),
        "pollutants": sorted(observations["pollutant"].dropna().unique()) if not observations.empty else [],
        "snapshot_bucket_minutes": bucket_minutes,
        "snapshot_freshness_minutes": freshness_minutes,
        "snapshot_timestamps": int(snapshots["timestamp"].nunique()) if not snapshots.empty else 0,
        "sources": read_source_statuses(settings),
    }


def materialize_snapshot_projection(settings: Settings) -> pd.DataFrame:
    sensors = write_real_sensor_geojson(settings)
    replace_sensors(settings, sensors)
    observations = read_observations(settings)
    if not observations.empty:
        observations["timestamp"] = pd.to_datetime(observations["timestamp"], errors="coerce")
        observations["received_at"] = pd.to_datetime(observations["received_at"], errors="coerce")
    snapshots = build_operational_snapshots(settings, observations)
    replace_snapshots(settings, snapshots)
    write_table(observations, settings.processed_dir / "real_sensor_observations.parquet")
    write_table(snapshots, settings.processed_dir / "campus_air_quality_estimates.parquet")
    metadata = _export_metadata(settings, observations, snapshots, sensors, read_raw_message_count(settings))
    output = settings.processed_dir / "realtime_ingestion_summary.json"
    ensure_dir(output.parent)
    output.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    write_metadata(settings, "last_export", metadata)
    write_ingestion_run(settings, metadata)
    publish_operational_event(
        settings,
        "snapshots.materialized",
        metadata,
        aggregate_type="snapshot_projection",
        aggregate_id=str(metadata.get("generated_at") or ""),
        occurred_at=str(metadata.get("generated_at") or ""),
    )
    publish_realtime_notification(settings, "snapshots.materialized", metadata)
    return snapshots


def _cursor_value(settings: Settings) -> int:
    metadata = read_metadata(settings)
    raw = metadata.get(OBSERVATION_CURSOR_KEY, 0)
    try:
        return int(raw or 0)
    except (TypeError, ValueError):
        return 0


def _write_cursor(settings: Settings, event_id: int) -> None:
    write_metadata(settings, OBSERVATION_CURSOR_KEY, int(event_id))


def project_pending_events(settings: Settings, batch_size: int = 500) -> dict[str, int]:
    last_seen = _cursor_value(settings)
    latest_processed = last_seen
    observation_changes = 0

    while True:
        events = read_operational_events(settings, after_event_id=latest_processed, limit=batch_size)
        if not events:
            break
        for event in events:
            latest_processed = int(event["event_id"])
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if event.get("event_type") == "observations.replaced":
                replace_observations(settings, _observation_frame(payload.get("observations") or []))
                observation_changes += 1
            elif event.get("event_type") == "observations.upserted":
                upsert_observations(settings, _observation_frame(payload.get("observations") or []))
                observation_changes += 1
        _write_cursor(settings, latest_processed)

    if observation_changes:
        snapshots = materialize_snapshot_projection(settings)
        _write_cursor(settings, read_latest_event_id(settings))
        return {
            "projected_events": max(latest_processed - last_seen, 0),
            "observation_changes": observation_changes,
            "snapshot_rows": int(len(snapshots)),
        }

    if latest_processed > last_seen:
        _write_cursor(settings, latest_processed)
    return {
        "projected_events": max(latest_processed - last_seen, 0),
        "observation_changes": 0,
        "snapshot_rows": int(len(read_snapshots(settings))),
    }


def rebuild_projections_from_event_log(settings: Settings, batch_size: int = 500) -> dict[str, int]:
    replace_observations(settings, pd.DataFrame(columns=OBSERVATION_COLUMNS))
    replace_snapshots(settings, pd.DataFrame())
    latest_processed = 0
    observation_changes = 0

    while True:
        events = read_operational_events(settings, after_event_id=latest_processed, limit=batch_size)
        if not events:
            break
        for event in events:
            latest_processed = int(event["event_id"])
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            if event.get("event_type") == "observations.replaced":
                replace_observations(settings, _observation_frame(payload.get("observations") or []))
                observation_changes += 1
            elif event.get("event_type") == "observations.upserted":
                upsert_observations(settings, _observation_frame(payload.get("observations") or []))
                observation_changes += 1

    _write_cursor(settings, latest_processed)
    snapshots = materialize_snapshot_projection(settings)
    _write_cursor(settings, read_latest_event_id(settings))
    return {
        "replayed_events": latest_processed,
        "observation_changes": observation_changes,
        "snapshot_rows": int(len(snapshots)),
    }
