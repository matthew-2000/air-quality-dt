from __future__ import annotations

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.ingestion.runtime import snapshot_settings


def _confidence_from_age_seconds(age_seconds: float, freshness_seconds: float) -> str:
    if age_seconds <= max(60.0, freshness_seconds / 3):
        return "alta"
    if age_seconds <= max(180.0, freshness_seconds * 0.7):
        return "media"
    return "bassa"


def build_operational_snapshots(settings: Settings, observations: pd.DataFrame) -> pd.DataFrame:
    if observations.empty:
        return observations.copy()

    bucket_minutes, freshness_minutes = snapshot_settings(settings)
    bucket = pd.Timedelta(minutes=bucket_minutes)
    freshness = pd.Timedelta(minutes=freshness_minutes)
    query_offset = pd.Timedelta(microseconds=1)

    frame = observations.copy()
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame["received_at"] = pd.to_datetime(frame["received_at"], errors="coerce")
    frame["timestamp"] = frame["timestamp"].astype("datetime64[ns]")
    frame["received_at"] = frame["received_at"].astype("datetime64[ns]")
    frame = frame.dropna(subset=["timestamp"]).sort_values(["pollutant", "timestamp", "received_at", "sensor_id"])
    if frame.empty:
        return frame

    rows: list[pd.DataFrame] = []
    freshness_seconds = freshness.total_seconds()

    for _pollutant, pollutant_frame in frame.groupby("pollutant", sort=True):
        pollutant_frame = pollutant_frame.copy()
        capable_sensors = max(1, int(pollutant_frame["sensor_id"].nunique()))
        first_bucket = pollutant_frame["timestamp"].min().floor(f"{bucket_minutes}min")
        last_bucket = pollutant_frame["timestamp"].max().floor(f"{bucket_minutes}min")
        snapshot_starts = pd.date_range(start=first_bucket, end=last_bucket, freq=f"{bucket_minutes}min")
        if snapshot_starts.empty:
            continue

        snapshot_frame = pd.DataFrame(
            {
                "timestamp": snapshot_starts,
                "snapshot_end": snapshot_starts + bucket,
                "query_time": snapshot_starts + bucket - query_offset,
            }
        )
        snapshot_frame["timestamp"] = snapshot_frame["timestamp"].astype("datetime64[ns]")
        snapshot_frame["snapshot_end"] = snapshot_frame["snapshot_end"].astype("datetime64[ns]")
        snapshot_frame["query_time"] = snapshot_frame["query_time"].astype("datetime64[ns]")

        per_sensor_rows: list[pd.DataFrame] = []
        for _sensor_id, sensor_frame in pollutant_frame.groupby("sensor_id", sort=False):
            sensor_frame = sensor_frame.sort_values(["timestamp", "received_at"]).reset_index(drop=True)
            matched = pd.merge_asof(
                snapshot_frame,
                sensor_frame,
                left_on="query_time",
                right_on="timestamp",
                direction="backward",
                tolerance=freshness,
            )
            matched = matched.dropna(subset=["sensor_id"]).copy()
            if matched.empty:
                continue
            matched["measured_at"] = matched["timestamp_y"]
            matched["timestamp"] = matched["timestamp_x"]
            matched = matched.drop(columns=["timestamp_x", "timestamp_y", "query_time"])
            per_sensor_rows.append(matched)

        if not per_sensor_rows:
            continue

        snapshot_rows = pd.concat(per_sensor_rows, ignore_index=True)
        snapshot_rows["reading_age_seconds"] = (
            (snapshot_rows["snapshot_end"] - snapshot_rows["measured_at"]).dt.total_seconds().clip(lower=0).round().astype(int)
        )
        snapshot_rows["snapshot_bucket_minutes"] = bucket_minutes
        snapshot_rows["snapshot_freshness_minutes"] = freshness_minutes
        snapshot_rows["confidence_label"] = snapshot_rows["reading_age_seconds"].map(
            lambda value: _confidence_from_age_seconds(float(value), freshness_seconds)
        )
        snapshot_rows["station_count"] = snapshot_rows.groupby("timestamp")["sensor_id"].transform("nunique").astype(int)
        snapshot_rows["capable_sensor_count"] = capable_sensors
        snapshot_rows["coverage_ratio"] = (snapshot_rows["station_count"] / capable_sensors).round(3)
        rows.append(snapshot_rows.drop(columns=["snapshot_end"]))

    if not rows:
        return pd.DataFrame(columns=[*observations.columns, "measured_at", "reading_age_seconds"])

    snapshots = pd.concat(rows, ignore_index=True)
    snapshots = snapshots.sort_values(["timestamp", "pollutant", "sensor_id"]).reset_index(drop=True)
    return snapshots
