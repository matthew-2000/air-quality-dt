from __future__ import annotations

from functools import lru_cache
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings, load_settings
from unisa_air_twin.gis import (
    available_timestamps,
    build_interpolation_grid,
    color_zone_geojson,
    sensor_snapshot,
    timestamp_window,
    value_color,
    window_frame,
    zone_delta_summary,
)
from unisa_air_twin.live_sensors import build_realtime_dataset, write_real_sensor_geojson
from unisa_air_twin.scenario import apply_scenario, scenario_summary
from unisa_air_twin.storage import geojson_points_to_frame, read_geojson, read_table
from unisa_air_twin.utils import read_json

SCENARIO_PRESETS: dict[str, dict[str, Any]] = {
    "Personalizzato": {
        "traffic_reduction": 0.2,
        "wind_multiplier": 1.0,
        "rain_event": False,
        "focus_zone": "all",
        "green_improvement": 0.0,
    },
    "Ora di punta al terminal bus": {
        "traffic_reduction": 0.45,
        "wind_multiplier": 1.0,
        "rain_event": False,
        "focus_zone": "mobilita",
        "green_improvement": 0.0,
    },
    "Parcheggio meno utilizzato": {
        "traffic_reduction": 0.35,
        "wind_multiplier": 1.0,
        "rain_event": False,
        "focus_zone": "parcheggio",
        "green_improvement": 0.05,
    },
    "Giornata di pioggia": {
        "traffic_reduction": 0.1,
        "wind_multiplier": 1.0,
        "rain_event": True,
        "focus_zone": "all",
        "green_improvement": 0.0,
    },
    "Vento forte": {
        "traffic_reduction": 0.0,
        "wind_multiplier": 1.8,
        "rain_event": False,
        "focus_zone": "all",
        "green_improvement": 0.0,
    },
    "Campus green mobility": {
        "traffic_reduction": 0.35,
        "wind_multiplier": 1.1,
        "rain_event": False,
        "focus_zone": "all",
        "green_improvement": 0.25,
    },
    "Nuova area verde nei parcheggi": {
        "traffic_reduction": 0.15,
        "wind_multiplier": 1.0,
        "rain_event": False,
        "focus_zone": "parcheggio",
        "green_improvement": 0.4,
    },
}


def format_zone(zone: str) -> str:
    labels = {
        "all": "tutto il campus",
        "amministrazione": "amministrazione",
        "didattica": "didattica",
        "mobilita": "mobilita",
        "parcheggio": "parcheggio",
        "servizi": "servizi",
        "studio": "studio",
        "verde": "verde",
        "campus": "campus",
    }
    return labels.get(zone, zone)


def frame_records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    if frame.empty:
        return []
    output = frame.copy()
    for column in output.select_dtypes(include=["datetime64[ns]", "datetimetz"]).columns:
        output[column] = output[column].dt.strftime("%Y-%m-%dT%H:%M:%S")
    output = output.where(pd.notna(output), None)
    return output.to_dict(orient="records")


def color_series(values: pd.Series, palette: str = "value") -> list[list[int]]:
    if values.empty:
        return []
    low = float(values.min())
    high = float(values.max())
    return [value_color(float(value), low, high, palette=palette) for value in values]


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


class TwinDataService:
    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or load_settings()
        self._loaded: dict[str, Any] | None = None

    def load(self) -> dict[str, Any]:
        if self._loaded is None:
            self._loaded = self._load_data()
        return self._loaded

    def refresh(self) -> dict[str, Any]:
        self._loaded = self._load_data()
        return self._loaded

    def _load_data(self) -> dict[str, Any]:
        sensors = geojson_points_to_frame(self.settings.processed_dir / "campus_real_sensors.geojson")
        if sensors.empty:
            sensors = write_real_sensor_geojson(self.settings)

        estimates = read_table(self.settings.processed_dir / "campus_air_quality_estimates.parquet")
        if estimates.empty:
            estimates = build_realtime_dataset(self.settings)
        if "timestamp" in estimates.columns:
            estimates["timestamp"] = pd.to_datetime(estimates["timestamp"], errors="coerce")
        if "measured_at" in estimates.columns:
            estimates["measured_at"] = pd.to_datetime(estimates["measured_at"], errors="coerce")
        if "received_at" in estimates.columns:
            estimates["received_at"] = pd.to_datetime(estimates["received_at"], errors="coerce")

        observations = read_table(self.settings.processed_dir / "real_sensor_observations.parquet")
        if observations.empty:
            build_realtime_dataset(self.settings)
            observations = read_table(self.settings.processed_dir / "real_sensor_observations.parquet")
        if "timestamp" in observations.columns:
            observations["timestamp"] = pd.to_datetime(observations["timestamp"], errors="coerce")
        if "received_at" in observations.columns:
            observations["received_at"] = pd.to_datetime(observations["received_at"], errors="coerce")

        stations = pd.DataFrame()
        schema_report = read_json(self.settings.processed_dir / "schema_report.json", default={"warnings": []})
        layers = {
            "buildings": read_geojson(self.settings.processed_dir / "campus_buildings.geojson"),
            "roads": read_geojson(self.settings.processed_dir / "campus_roads.geojson"),
            "green": read_geojson(self.settings.processed_dir / "campus_green.geojson"),
            "transport": read_geojson(self.settings.processed_dir / "campus_transport.geojson"),
            "parking": read_geojson(self.settings.processed_dir / "campus_parking.geojson"),
        }
        ingestion_summary = read_json(
            self.settings.processed_dir / "realtime_ingestion_summary.json",
            default={"rows": 0, "sensors": 0, "pollutants": []},
        )

        return {
            "estimates": estimates,
            "observations": observations,
            "sensors": sensors,
            "stations": stations,
            "schema_report": schema_report if isinstance(schema_report, dict) else {"warnings": []},
            "layers": layers,
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
        timestamps = self.timestamps(default_pollutant)
        latest_timestamp = timestamps[-1] if timestamps else None
        latest_snapshot = self.snapshot(default_pollutant, latest_timestamp) if latest_timestamp else pd.DataFrame()
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
        coverage_by_pollutant: list[dict[str, Any]] = []
        for pollutant in ordered:
            pollutant_snapshot = self.snapshot(pollutant, latest_timestamp) if latest_timestamp else pd.DataFrame()
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
            "source": "Sensori reali UNISA",
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
            "raw_rows": int(ingestion.get("raw_rows", 0)),
            "snapshot_rows": int(ingestion.get("snapshot_rows", len(estimates))),
            "sensors": int(len(sensors)),
            "active_sensors": active_sensors,
            "capable_sensors": capable_sensors,
            "coverage_ratio": coverage_ratio,
            "stations": int(len(stations)),
            "coverage_by_pollutant": coverage_by_pollutant,
            "layer_counts": layer_counts,
            "ingestion": ingestion,
            "warnings": data["schema_report"].get("warnings", []),
            "mode": "real_only",
        }

    def timestamps(self, pollutant: str) -> list[str]:
        estimates = self.load()["estimates"]
        return [pd.Timestamp(ts).strftime("%Y-%m-%dT%H:%M:%S") for ts in available_timestamps(estimates, pollutant)]

    def snapshot(self, pollutant: str, timestamp: str | pd.Timestamp) -> pd.DataFrame:
        return sensor_snapshot(self.load()["estimates"], pollutant, pd.Timestamp(timestamp))

    def map_payload(self, pollutant: str, timestamp: str | pd.Timestamp, resolution: int = 24) -> dict[str, Any]:
        data = self.load()
        snapshot = self.snapshot(pollutant, timestamp).copy()
        if not snapshot.empty:
            snapshot["status"] = snapshot["reading_age_seconds"].map(sensor_status)
            snapshot["reading_age_minutes"] = (pd.to_numeric(snapshot["reading_age_seconds"], errors="coerce") / 60.0).round(1)
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
            "grid": [],
            "reliability_grid": [],
            "zones": {"type": "FeatureCollection", "features": []},
            "layers": data["layers"],
            "stations": frame_records(stations),
            "meta": meta,
        }

    def scenario_payload(
        self,
        pollutant: str,
        timestamp: str | pd.Timestamp,
        traffic_reduction: float = 0.2,
        wind_multiplier: float = 1.0,
        rain_event: bool = False,
        focus_zone: str = "all",
        green_improvement: float = 0.0,
        window_label: str = "Solo ora selezionata",
        resolution: int = 24,
    ) -> dict[str, Any]:
        data = self.load()
        timestamps = [pd.Timestamp(ts) for ts in available_timestamps(data["estimates"], pollutant)]
        selected_timestamp = pd.Timestamp(timestamp)
        selected_window = timestamp_window(timestamps, selected_timestamp, window_label)
        scenario_window = window_frame(data["estimates"], pollutant, selected_window)
        baseline = self.snapshot(pollutant, selected_timestamp)
        scenario = apply_scenario(
            baseline,
            self.settings,
            traffic_reduction=traffic_reduction,
            wind_multiplier=wind_multiplier,
            rain_event=rain_event,
            focus_zone=focus_zone,
            green_improvement=green_improvement,
        )
        scenario_window_result = apply_scenario(
            scenario_window,
            self.settings,
            traffic_reduction=traffic_reduction,
            wind_multiplier=wind_multiplier,
            rain_event=rain_event,
            focus_zone=focus_zone,
            green_improvement=green_improvement,
        )
        if not scenario.empty:
            scenario["delta_color"] = color_series(scenario["delta"], palette="delta")
        scenario_grid = build_interpolation_grid(scenario, value_column="scenario_value", resolution=resolution)
        delta_grid = build_interpolation_grid(
            scenario.rename(columns={"delta": "delta_value"}),
            value_column="delta_value",
            resolution=resolution,
        )
        zone_summary = zone_delta_summary(scenario)
        zone_delta_geojson = color_zone_geojson(data["zones_geojson"], zone_summary, "mean_delta")
        timeline = pd.DataFrame()
        if not scenario_window_result.empty:
            timeline = (
                scenario_window_result.groupby("timestamp", as_index=False)
                .agg(baseline=("estimated_value", "mean"), scenario=("scenario_value", "mean"))
                .sort_values("timestamp")
            )
        return {
            "summary": scenario_summary(scenario),
            "snapshot": frame_records(scenario),
            "scenario_grid": frame_records(scenario_grid),
            "delta_grid": frame_records(delta_grid),
            "zone_summary": frame_records(zone_summary),
            "zone_delta_geojson": zone_delta_geojson,
            "timeline": frame_records(timeline),
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

        latest_environment = raw_history.sort_values("timestamp").tail(1)
        latest_environment_row = latest_environment.iloc[0].to_dict() if not latest_environment.empty else {}

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
