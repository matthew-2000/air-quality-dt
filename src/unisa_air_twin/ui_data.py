from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings, load_settings
from unisa_air_twin.gis import (
    available_timestamps,
    build_interpolation_grid,
    build_reliability_grid,
    sensor_snapshot,
)
from unisa_air_twin.live_sensors import (
    build_operational_snapshots,
    load_sensor_catalog,
)
from unisa_air_twin.operational_store import (
    read_metadata,
    read_observations,
    read_raw_message_count,
    read_sensors,
)
from unisa_air_twin.storage import geojson_points_to_frame, read_geojson
from unisa_air_twin.utils import read_json


def frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    output = frame.copy()
    for column in output.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        output[column] = output[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    output = output.where(pd.notna(output), None)
    return output.to_dict(orient="records")


def sensor_status(age_seconds: Any) -> str:
    value = pd.to_numeric(age_seconds, errors="coerce")
    if pd.isna(value):
        return "unknown"
    if float(value) <= 60:
        return "fresh"
    if float(value) <= 180:
        return "recent"
    return "aging"


def ordered_pollutants(values: list[str], configured: list[str]) -> list[str]:
    preferred = ["pm10", "pm25", "pm1", *configured]
    ordered: list[str] = []
    for pollutant in preferred:
        if pollutant in values and pollutant not in ordered:
            ordered.append(pollutant)
    for pollutant in values:
        if pollutant not in ordered:
            ordered.append(pollutant)
    return ordered


def live_feed_status(settings: Settings, latest_received: str | None) -> dict[str, Any]:
    broker = settings.live_sensors.get("broker", {})
    required_keys = [
        broker.get("host_env", "UNISA_MQTT_HOST"),
        broker.get("port_env", "UNISA_MQTT_PORT"),
        broker.get("topic_env", "UNISA_MQTT_TOPIC"),
        broker.get("username_env", "UNISA_MQTT_USERNAME"),
        broker.get("password_env", "UNISA_MQTT_PASSWORD"),
    ]
    missing = [key for key in required_keys if not os.environ.get(key)]
    status = "unconfigured" if missing else "unknown"
    age_minutes: int | None = None
    latest_value: str | None = latest_received

    if latest_received:
        latest_ts = pd.to_datetime(latest_received, errors="coerce")
        if pd.notna(latest_ts):
            now = pd.Timestamp.now(tz=settings.project.get("timezone", "Europe/Rome")).tz_localize(None)
            age_minutes = int(max((now - pd.Timestamp(latest_ts)).total_seconds(), 0) // 60)
            status = "live" if not missing and age_minutes <= 15 else "stale"
            latest_value = pd.Timestamp(latest_ts).strftime("%Y-%m-%dT%H:%M:%S")

    return {
        "status": status,
        "configured": not missing,
        "missing_env": missing,
        "latest_received_at": latest_value,
        "age_minutes": age_minutes,
    }


class TwinDataService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self._static_loaded: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        return {**self._load_static_data(), **self._load_dynamic_data()}

    def refresh(self) -> dict[str, Any]:
        self._static_loaded = None
        return self.load()

    def _load_static_data(self) -> dict[str, Any]:
        if self._static_loaded is not None:
            return self._static_loaded
        stations = pd.DataFrame()
        schema_report = read_json(self.settings.processed_dir / "schema_report.json", default={"warnings": []})
        layers = {
            "buildings": read_geojson(self.settings.processed_dir / "campus_buildings.geojson"),
            "roads": read_geojson(self.settings.processed_dir / "campus_roads.geojson"),
            "green": read_geojson(self.settings.processed_dir / "campus_green.geojson"),
            "transport": read_geojson(self.settings.processed_dir / "campus_transport.geojson"),
            "parking": read_geojson(self.settings.processed_dir / "campus_parking.geojson"),
        }
        self._static_loaded = {
            "stations": stations,
            "schema_report": schema_report if isinstance(schema_report, dict) else {"warnings": []},
            "layers": layers,
        }
        return self._static_loaded

    def _load_dynamic_data(self) -> dict[str, Any]:
        sensors = read_sensors(self.settings)
        observations = read_observations(self.settings)

        if sensors.empty:
            sensors = geojson_points_to_frame(self.settings.processed_dir / "campus_real_sensors.geojson")
            if sensors.empty:
                sensors = load_sensor_catalog(self.settings)

        if "timestamp" in observations.columns:
            observations["timestamp"] = pd.to_datetime(observations["timestamp"], errors="coerce")
        if "received_at" in observations.columns:
            observations["received_at"] = pd.to_datetime(observations["received_at"], errors="coerce")
        if "downloaded_at" in observations.columns:
            observations["downloaded_at"] = pd.to_datetime(observations["downloaded_at"], errors="coerce")

        estimates = build_operational_snapshots(self.settings, observations)
        if "timestamp" in estimates.columns:
            estimates["timestamp"] = pd.to_datetime(estimates["timestamp"], errors="coerce")
        if "measured_at" in estimates.columns:
            estimates["measured_at"] = pd.to_datetime(estimates["measured_at"], errors="coerce")
        if "received_at" in estimates.columns:
            estimates["received_at"] = pd.to_datetime(estimates["received_at"], errors="coerce")

        ingestion_summary = read_metadata(self.settings).get("last_export")
        if not isinstance(ingestion_summary, dict):
            ingestion_summary = read_json(
                self.settings.processed_dir / "realtime_ingestion_summary.json",
                default={"rows": 0, "sensors": 0, "pollutants": []},
            )

        return {
            "estimates": estimates,
            "observations": observations,
            "sensors": sensors,
            "raw_message_rows": read_raw_message_count(self.settings),
            "ingestion_summary": ingestion_summary if isinstance(ingestion_summary, dict) else {},
        }

    def summary(self) -> dict[str, Any]:
        data = self.load()
        estimates = data["estimates"]
        stations = data["stations"]
        pollutants = sorted(estimates["pollutant"].dropna().unique()) if not estimates.empty else []
        configured_order = self.settings.model.get("pollutants", [])
        ordered = ordered_pollutants(pollutants, configured_order)
        default_pollutant = ordered[0] if ordered else "pm10"
        timestamps = self._timestamps_from_estimates(estimates, default_pollutant)
        latest_timestamp = timestamps[-1] if timestamps else None
        latest_snapshot = (
            self._snapshot_from_estimates(estimates, default_pollutant, latest_timestamp)
            if latest_timestamp
            else pd.DataFrame()
        )
        sensors = data["sensors"]
        latest_received = (
            pd.to_datetime(estimates["received_at"], errors="coerce").max().strftime("%Y-%m-%dT%H:%M:%S")
            if "received_at" in estimates.columns and not estimates.empty
            else latest_timestamp
        )
        active_sensors = int(latest_snapshot["sensor_id"].nunique()) if "sensor_id" in latest_snapshot.columns else 0
        capable_sensors = (
            int(pd.to_numeric(latest_snapshot["capable_sensor_count"], errors="coerce").max())
            if "capable_sensor_count" in latest_snapshot.columns and not latest_snapshot.empty
            else active_sensors
        )
        coverage_ratio = round(float(active_sensors) / capable_sensors, 3) if capable_sensors else 0.0
        ingestion = data["ingestion_summary"]
        live_feed = live_feed_status(self.settings, latest_received)
        sensor_health = self._sensor_health(data["sensors"], data["observations"])
        coverage_by_pollutant: list[dict[str, Any]] = []
        for pollutant in ordered:
            pollutant_snapshot = (
                self._snapshot_from_estimates(estimates, pollutant, latest_timestamp)
                if latest_timestamp
                else pd.DataFrame()
            )
            pollutant_active = int(pollutant_snapshot["sensor_id"].nunique()) if "sensor_id" in pollutant_snapshot.columns else 0
            pollutant_capable = (
                int(pd.to_numeric(pollutant_snapshot["capable_sensor_count"], errors="coerce").max())
                if "capable_sensor_count" in pollutant_snapshot.columns and not pollutant_snapshot.empty
                else pollutant_active
            )
            pollutant_coverage = round(float(pollutant_active) / pollutant_capable, 3) if pollutant_capable else 0.0
            coverage_by_pollutant.append(
                {
                    "pollutant": pollutant,
                    "active_sensors": pollutant_active,
                    "capable_sensors": pollutant_capable,
                    "coverage_ratio": pollutant_coverage,
                }
            )
        layer_counts = {name: int(len((layer or {}).get("features", []))) for name, layer in data["layers"].items()}
        return {
            "project": "UNISA Air Quality Digital Twin",
            "source": "UNISA AQDT",
            "campus": {
                "name": self.settings.campus.get("name", "Campus di Fisciano"),
                "latitude": self.settings.campus.get("fallback_latitude"),
                "longitude": self.settings.campus.get("fallback_longitude"),
            },
            "pollutants": ordered,
            "default_pollutant": default_pollutant,
            "latest_timestamp": latest_timestamp,
            "latest_received_at": latest_received,
            "rows": int(len(estimates)),
            "raw_rows": int(ingestion.get("observation_rows", ingestion.get("raw_rows", len(data["observations"])))),
            "observation_rows": int(ingestion.get("observation_rows", ingestion.get("raw_rows", len(data["observations"])))),
            "raw_message_rows": int(ingestion.get("raw_message_rows", data["raw_message_rows"])),
            "snapshot_rows": int(ingestion.get("snapshot_rows", len(estimates))),
            "sensors": int(len(sensors)),
            "active_sensors": active_sensors,
            "capable_sensors": capable_sensors,
            "coverage_ratio": coverage_ratio,
            "sensor_health": sensor_health,
            "stations": int(len(stations)),
            "coverage_by_pollutant": coverage_by_pollutant,
            "layer_counts": layer_counts,
            "ingestion": ingestion,
            "live_feed": live_feed,
            "warnings": data["schema_report"].get("warnings", []),
            "mode": "real_only",
        }

    def _sensor_health(self, sensors: pd.DataFrame, observations: pd.DataFrame) -> list[dict[str, Any]]:
        if sensors.empty:
            return []
        sensor_rows = sensors.copy()
        if observations.empty or "sensor_id" not in observations.columns:
            return [
                {
                    "sensor_id": row.get("sensor_id"),
                    "sensor_name": row.get("name") or row.get("sensor_id"),
                    "status": "silent",
                    "latest_received_at": None,
                    "latest_measured_at": None,
                    "pollutants": [],
                }
                for row in sensor_rows.to_dict(orient="records")
            ]

        obs = observations.copy()
        obs["timestamp"] = pd.to_datetime(obs.get("timestamp"), errors="coerce")
        obs["received_at"] = pd.to_datetime(obs.get("received_at"), errors="coerce")
        latest_by_sensor = (
            obs.dropna(subset=["sensor_id"])
            .sort_values(["received_at", "timestamp"])
            .groupby("sensor_id", as_index=False)
            .tail(1)
            .set_index("sensor_id")
        )
        pollutants_by_sensor = obs.groupby("sensor_id")["pollutant"].apply(lambda values: sorted(set(values.dropna().astype(str))))
        rows: list[dict[str, Any]] = []
        for sensor in sensor_rows.to_dict(orient="records"):
            sensor_id = str(sensor.get("sensor_id"))
            latest = latest_by_sensor.loc[sensor_id] if sensor_id in latest_by_sensor.index else None
            latest_received = latest.get("received_at") if latest is not None else None
            age_seconds = None
            if latest_received is not None and pd.notna(latest_received):
                now = pd.Timestamp.now(tz=self.settings.project.get("timezone", "Europe/Rome")).tz_localize(None)
                age_seconds = max((now - pd.Timestamp(latest_received)).total_seconds(), 0)
            rows.append(
                {
                    "sensor_id": sensor_id,
                    "sensor_name": sensor.get("name") or sensor_id,
                    "status": "silent" if latest is None else sensor_status(age_seconds),
                    "latest_received_at": pd.Timestamp(latest_received).strftime("%Y-%m-%dT%H:%M:%S")
                    if latest_received is not None and pd.notna(latest_received)
                    else None,
                    "latest_measured_at": pd.Timestamp(latest.get("timestamp")).strftime("%Y-%m-%dT%H:%M:%S")
                    if latest is not None and pd.notna(latest.get("timestamp"))
                    else None,
                    "pollutants": pollutants_by_sensor.get(sensor_id, []),
                }
            )
        return rows

    def timestamps(self, pollutant: str) -> list[str]:
        return self._timestamps_from_estimates(self.load()["estimates"], pollutant)

    def snapshot(self, pollutant: str, timestamp: str | pd.Timestamp) -> pd.DataFrame:
        return self._snapshot_from_estimates(self.load()["estimates"], pollutant, timestamp)

    def _timestamps_from_estimates(self, estimates: pd.DataFrame, pollutant: str) -> list[str]:
        return [pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S") for ts in available_timestamps(estimates, pollutant)]

    def _snapshot_from_estimates(
        self,
        estimates: pd.DataFrame,
        pollutant: str,
        timestamp: str | pd.Timestamp,
    ) -> pd.DataFrame:
        return sensor_snapshot(estimates, pollutant, pd.Timestamp(timestamp))

    def map_payload(self, pollutant: str, timestamp: str | pd.Timestamp, resolution: int = 24) -> dict[str, Any]:
        data = self.load()
        snapshot = self._snapshot_from_estimates(data["estimates"], pollutant, timestamp).copy()
        if not snapshot.empty:
            snapshot["status"] = snapshot["reading_age_seconds"].map(sensor_status)
            snapshot["reading_age_minutes"] = (pd.to_numeric(snapshot["reading_age_seconds"], errors="coerce") / 60.0).round(1)
        grid = build_interpolation_grid(snapshot, resolution=resolution)
        reliability_grid = build_reliability_grid(snapshot, resolution=resolution)
        ages = pd.to_numeric(snapshot["reading_age_seconds"], errors="coerce") if "reading_age_seconds" in snapshot.columns else pd.Series(dtype=float)
        values = pd.to_numeric(snapshot["estimated_value"], errors="coerce") if "estimated_value" in snapshot.columns else pd.Series(dtype=float)
        meta = {
            "active_sensors": int(snapshot["sensor_id"].nunique()) if "sensor_id" in snapshot.columns else 0,
            "capable_sensors": (
                int(pd.to_numeric(snapshot["capable_sensor_count"], errors="coerce").max())
                if "capable_sensor_count" in snapshot.columns and not snapshot.empty
                else 0
            ),
            "coverage_ratio": (
                round(float(pd.to_numeric(snapshot["coverage_ratio"], errors="coerce").max()), 3)
                if "coverage_ratio" in snapshot.columns and not snapshot.empty
                else 0.0
            ),
            "fresh_sensors": int(snapshot["status"].eq("fresh").sum()) if "status" in snapshot.columns else 0,
            "recent_sensors": int(snapshot["status"].eq("recent").sum()) if "status" in snapshot.columns else 0,
            "aging_sensors": int(snapshot["status"].eq("aging").sum()) if "status" in snapshot.columns else 0,
            "median_age_seconds": int(ages.median()) if not ages.empty else 0,
            "min_value": round(float(values.min()), 3) if not values.empty else None,
            "max_value": round(float(values.max()), 3) if not values.empty else None,
        }
        stations = data["stations"].dropna(subset=["lat", "lon"]) if not data["stations"].empty else pd.DataFrame()
        return {
            "snapshot": frame_records(snapshot),
            "grid": frame_records(grid),
            "reliability_grid": frame_records(reliability_grid),
            "zones": {"type": "FeatureCollection", "features": []},
            "layers": data["layers"],
            "stations": frame_records(stations),
            "meta": meta,
        }

    def sensor_detail(self, sensor_id: str, timestamp: str | pd.Timestamp) -> dict[str, Any]:
        data = self.load()
        selected_timestamp = pd.Timestamp(timestamp)
        sensors = data["sensors"]
        sensor_frame = sensors[sensors["sensor_id"] == sensor_id].copy()
        sensor_meta = sensor_frame.iloc[0].to_dict() if not sensor_frame.empty else {"sensor_id": sensor_id}

        estimates = data["estimates"]
        snapshot = estimates[(estimates["sensor_id"] == sensor_id) & (estimates["timestamp"] == selected_timestamp)].copy()
        configured_order = self.settings.model.get("pollutants", [])
        if not snapshot.empty:
            snapshot["status"] = snapshot["reading_age_seconds"].map(sensor_status)
            order_map = {pollutant: index for index, pollutant in enumerate(ordered_pollutants(snapshot["pollutant"].dropna().unique().tolist(), configured_order))}
            snapshot["pollutant_order"] = snapshot["pollutant"].map(lambda value: order_map.get(str(value), 999))
            snapshot = snapshot.sort_values(["pollutant_order", "pollutant"]).drop(columns=["pollutant_order"])

        observations = data["observations"]
        raw_history = observations[observations["sensor_id"] == sensor_id].copy()
        raw_history = raw_history.sort_values(["timestamp", "pollutant"])
        history_payload: dict[str, list[dict[str, Any]]] = {}
        for pollutant in ordered_pollutants(raw_history["pollutant"].dropna().unique().tolist(), configured_order):
            subset = raw_history[raw_history["pollutant"] == pollutant].sort_values("timestamp")
            history_payload[pollutant] = frame_records(subset.tail(18))

        selected_environment = raw_history[raw_history["timestamp"] == selected_timestamp].sort_values("received_at").tail(1)
        if selected_environment.empty:
            selected_environment = raw_history.sort_values("timestamp").tail(1)
        latest_environment_row = selected_environment.iloc[0].to_dict() if not selected_environment.empty else {}

        return {
            "sensor": sensor_meta,
            "timestamp": selected_timestamp.strftime("%Y-%m-%dT%H:%M:%S"),
            "latest_values": frame_records(snapshot),
            "history": history_payload,
            "environment": {
                "temperature": latest_environment_row.get("temperature"),
                "humidity": latest_environment_row.get("humidity"),
                "num_devices_sniffed": latest_environment_row.get("num_devices_sniffed"),
                "received_at": pd.Timestamp(latest_environment_row["received_at"]).strftime("%Y-%m-%dT%H:%M:%S")
                if latest_environment_row.get("received_at") is not None and pd.notna(latest_environment_row.get("received_at"))
                else None,
            },
        }

    def timeseries(self, pollutant: str, sensor_name: str) -> list[dict[str, Any]]:
        observations = self.load()["observations"]
        if observations.empty:
            return []
        subset = observations[(observations["pollutant"] == pollutant) & (observations["sensor_name"] == sensor_name)]
        return frame_records(subset.sort_values("timestamp"))


@lru_cache(maxsize=1)
def get_twin_service() -> TwinDataService:
    return TwinDataService()
