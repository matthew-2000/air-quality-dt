from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.external_sources import (
    enrich_measurement,
    green_index_for_point,
    load_external_context,
)
from unisa_air_twin.ingestion.catalog import load_sensor_catalog
from unisa_air_twin.ingestion.runtime import configured_path, timestamp_guard_settings
from unisa_air_twin.operational_store import replace_sensors
from unisa_air_twin.shared.constants import POLLUTANT_FIELDS, SOURCE_NAME, SOURCE_URL
from unisa_air_twin.utils import utc_now_iso


def _local_timestamp(value: Any, settings: Settings) -> pd.Timestamp:
    if value is None or not str(value).strip():
        return pd.NaT

    timezone = settings.project.get("timezone", "Europe/Rome")
    numeric = pd.to_numeric(value, errors="coerce")
    if pd.notna(numeric):
        ts = pd.to_datetime(float(numeric), unit="s", utc=True, errors="coerce")
        if pd.isna(ts):
            return pd.NaT
        return pd.Timestamp(ts).tz_convert(timezone).tz_localize(None).floor("s")

    ts = pd.to_datetime(value, errors="coerce")
    if pd.isna(ts):
        return pd.NaT
    timestamp = pd.Timestamp(ts)
    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_convert(timezone).tz_localize(None)
    return timestamp.floor("s")


def _read_csv_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    frame = pd.read_csv(path)
    return frame.to_dict(orient="records")


def _read_jsonl_records(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rows.append(json.loads(line))
    return rows


def read_mqtt_records(settings: Settings) -> pd.DataFrame:
    records = [
        *_read_csv_records(configured_path(settings, "mqtt_csv_path")),
        *_read_jsonl_records(configured_path(settings, "mqtt_jsonl_path")),
    ]
    if not records:
        return pd.DataFrame(columns=["received_at", "topic", "payload"])
    frame = pd.DataFrame(records)
    if "timestamp" in frame.columns:
        frame = frame.rename(columns={"timestamp": "received_at"})
    for column in ["received_at", "topic", "payload"]:
        if column not in frame.columns:
            frame[column] = None
    return frame.drop_duplicates(subset=["received_at", "topic", "payload"]).reset_index(drop=True)


def _sensor_lookup(settings: Settings) -> dict[str, dict[str, Any]]:
    sensors = load_sensor_catalog(settings)
    if sensors.empty:
        return {}
    replace_sensors(settings, sensors)
    return sensors.set_index("sensor_id").to_dict(orient="index")


def _normalize_payload_record(
    settings: Settings,
    payload: dict[str, Any],
    topic: str,
    received_at_value: Any,
    metadata: dict[str, dict[str, Any]],
    ingested_at: str,
    external_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    sensor_id = str(payload.get("ID") or topic or "").strip()
    if not sensor_id:
        return []
    sensor = metadata.get(sensor_id, {})
    received_at = _local_timestamp(received_at_value, settings)
    measured_at = _local_timestamp(payload.get("timestamp"), settings)
    if pd.isna(measured_at):
        measured_at = received_at
    max_future_skew_seconds = timestamp_guard_settings(settings)
    if (
        pd.notna(received_at)
        and pd.notna(measured_at)
        and max_future_skew_seconds >= 0
        and measured_at > received_at + pd.Timedelta(seconds=max_future_skew_seconds)
    ):
        measured_at = received_at
    if pd.isna(measured_at):
        return []
    lat = sensor.get("lat")
    lon = sensor.get("lon")
    if lat is None or lon is None:
        return []

    traffic_index = min(max(float(payload.get("num_devices_sniffed") or 0.0) / 80.0, 0.0), 1.0)
    green_index = green_index_for_point(settings, float(lat), float(lon))
    context = external_context or {}
    rows: list[dict[str, Any]] = []
    for raw_name, pollutant in POLLUTANT_FIELDS.items():
        value = pd.to_numeric(payload.get(raw_name), errors="coerce")
        if pd.isna(value):
            continue
        base_value = round(float(value), 3)
        enriched = enrich_measurement(
            settings,
            pollutant=pollutant,
            base_value=base_value,
            traffic_index=float(traffic_index),
            green_index=float(green_index),
            context=context,
        )
        rows.append(
            {
                "timestamp": measured_at,
                "received_at": received_at if pd.notna(received_at) else measured_at,
                "sensor_id": sensor_id,
                "sensor_name": sensor.get("name", sensor_id),
                "lat": float(lat),
                "lon": float(lon),
                "zone": sensor.get("zone", "campus"),
                "pollutant": pollutant,
                "base_value": base_value,
                "estimated_value": enriched["estimated_value"],
                "temperature": pd.to_numeric(payload.get("temperatura"), errors="coerce"),
                "humidity": pd.to_numeric(payload.get("umidita"), errors="coerce"),
                "num_devices_sniffed": int(payload.get("num_devices_sniffed") or 0),
                "traffic_index": round(float(traffic_index), 3),
                "green_index": round(float(green_index), 3),
                "wind_speed_10m": enriched["wind_speed_10m"],
                "precipitation": enriched["precipitation"],
                "traffic_component": enriched["traffic_component"],
                "green_component": enriched["green_component"],
                "wind_component": enriched["wind_component"],
                "rain_component": enriched["rain_component"],
                "background_value": enriched["background_value"],
                "background_source": enriched["background_source"],
                "station_count": 1,
                "nearest_station_km": 0.0,
                "mean_station_distance_km": 0.0,
                "uncertainty_score": enriched["uncertainty_score"],
                "confidence_label": "alta",
                "source": SOURCE_NAME,
                "source_url": enriched["source_url"] or SOURCE_URL,
                "downloaded_at": ingested_at,
                "is_real": True,
            }
        )
    return rows


def normalize_mqtt_observations(settings: Settings) -> pd.DataFrame:
    metadata = _sensor_lookup(settings)
    external_context = load_external_context(settings)
    rows: list[dict[str, Any]] = []
    ingested_at = utc_now_iso()
    for _, record in read_mqtt_records(settings).iterrows():
        payload_value = record.get("payload")
        try:
            payload = json.loads(payload_value) if isinstance(payload_value, str) else dict(payload_value or {})
        except (TypeError, json.JSONDecodeError):
            continue
        rows.extend(
            _normalize_payload_record(
                settings,
                payload,
                str(record.get("topic") or ""),
                record.get("received_at"),
                metadata,
                ingested_at,
                external_context,
            )
        )
    observations = pd.DataFrame(rows)
    if not observations.empty:
        observations = observations.sort_values(["timestamp", "sensor_id", "pollutant"]).reset_index(drop=True)
        observations = observations.drop_duplicates(
            subset=["timestamp", "received_at", "sensor_id", "pollutant"],
            keep="last",
        ).reset_index(drop=True)
    return observations
