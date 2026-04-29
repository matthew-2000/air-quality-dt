from __future__ import annotations

import csv
import json
import os
import time
from pathlib import Path
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.storage import read_geojson, write_table
from unisa_air_twin.utils import ensure_dir, project_path, utc_now_iso
from unisa_air_twin.zones import create_campus_zones

SOURCE_NAME = "unisa_live_mqtt"
SOURCE_URL = "configured_mqtt_broker"

POLLUTANT_FIELDS = {
    "pm1": "pm1",
    "pm2_5": "pm25",
    "pm2.5": "pm25",
    "pm25": "pm25",
    "pm10": "pm10",
    "voc_index": "voc_index",
    "nox_index": "nox_index",
}


def _configured_path(settings: Settings, key: str) -> Path:
    raw_config = settings.live_sensors.get("raw", {})
    value = raw_config.get(key)
    if not value:
        return settings.raw_dir / "live_sensors" / key.replace("_path", "")
    path = Path(value)
    return path if path.is_absolute() else project_path(path)


def _local_timestamp(value: Any, settings: Settings) -> pd.Timestamp:
    if value is not None and str(value).strip():
        numeric = pd.to_numeric(value, errors="coerce")
        if pd.notna(numeric):
            ts = pd.to_datetime(float(numeric), unit="s", utc=True, errors="coerce")
        else:
            ts = pd.to_datetime(value, utc=True, errors="coerce")
    else:
        ts = pd.NaT
    if pd.isna(ts):
        return pd.NaT
    timezone = settings.project.get("timezone", "Europe/Rome")
    return pd.Timestamp(ts).tz_convert(timezone).tz_localize(None).floor("s")


def _zone_for_point(settings: Settings, lat: float, lon: float) -> str:
    zones_path = settings.processed_dir / "campus_zones.geojson"
    if not zones_path.exists():
        create_campus_zones(settings)
    zones = read_geojson(zones_path)
    fallback_zone = "campus"
    nearest_zone = fallback_zone
    nearest_distance = float("inf")
    for feature in zones.get("features", []):
        props = feature.get("properties") or {}
        coords = (feature.get("geometry") or {}).get("coordinates") or []
        ring = coords[0] if coords else []
        if not ring:
            continue
        lons = [point[0] for point in ring]
        lats = [point[1] for point in ring]
        zone = str(props.get("zone") or fallback_zone)
        if min(lats) <= lat <= max(lats) and min(lons) <= lon <= max(lons):
            return zone
        center_lat = float(props.get("center_lat", sum(lats) / len(lats)))
        center_lon = float(props.get("center_lon", sum(lons) / len(lons)))
        distance = (center_lat - lat) ** 2 + (center_lon - lon) ** 2
        if distance < nearest_distance:
            nearest_zone = zone
            nearest_distance = distance
    return nearest_zone


def load_sensor_catalog(settings: Settings) -> pd.DataFrame:
    metadata_path = _configured_path(settings, "sensor_metadata_path")
    if not metadata_path.exists():
        return pd.DataFrame(columns=["sensor_id", "name", "lat", "lon", "zone"])
    payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    downloaded_at = utc_now_iso()
    for item in payload if isinstance(payload, list) else []:
        sensor_id = str(item.get("ID") or item.get("id") or "").strip()
        lat = pd.to_numeric(item.get("lat"), errors="coerce")
        lon = pd.to_numeric(item.get("lon"), errors="coerce")
        if not sensor_id or pd.isna(lat) or pd.isna(lon):
            continue
        zone = _zone_for_point(settings, float(lat), float(lon))
        rows.append(
            {
                "sensor_id": sensor_id,
                "name": f"Sensore {sensor_id[-6:]}",
                "type": "real",
                "lat": float(lat),
                "lon": float(lon),
                "zone": zone,
                "description": "Sensore fisico UNISA collegato al broker MQTT configurato.",
                "coordinate_quality": "measured",
                "source": SOURCE_NAME,
                "source_url": SOURCE_URL,
                "downloaded_at": downloaded_at,
                "is_real": True,
            }
        )
    return pd.DataFrame(rows)


def write_real_sensor_geojson(settings: Settings, sensors: pd.DataFrame | None = None) -> pd.DataFrame:
    sensor_frame = load_sensor_catalog(settings) if sensors is None else sensors.copy()
    features = []
    for _, sensor in sensor_frame.iterrows():
        properties = sensor.to_dict()
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(sensor["lon"]), float(sensor["lat"])]},
                "properties": properties,
            }
        )
    output = settings.processed_dir / "campus_real_sensors.geojson"
    ensure_dir(output.parent)
    output.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    write_table(sensor_frame, settings.processed_dir / "real_sensor_metadata.parquet")
    return sensor_frame


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
        *_read_csv_records(_configured_path(settings, "mqtt_csv_path")),
        *_read_jsonl_records(_configured_path(settings, "mqtt_jsonl_path")),
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


def normalize_mqtt_observations(settings: Settings) -> pd.DataFrame:
    sensors = load_sensor_catalog(settings)
    metadata = sensors.set_index("sensor_id").to_dict(orient="index") if not sensors.empty else {}
    rows: list[dict[str, Any]] = []
    ingested_at = utc_now_iso()
    for _, record in read_mqtt_records(settings).iterrows():
        payload_value = record.get("payload")
        try:
            payload = json.loads(payload_value) if isinstance(payload_value, str) else dict(payload_value or {})
        except (TypeError, json.JSONDecodeError):
            continue
        sensor_id = str(payload.get("ID") or record.get("topic") or "").strip()
        if not sensor_id:
            continue
        sensor = metadata.get(sensor_id, {})
        received_at = _local_timestamp(record.get("received_at"), settings)
        measured_at = _local_timestamp(payload.get("timestamp"), settings)
        if pd.isna(measured_at):
            measured_at = received_at
        if pd.isna(measured_at):
            continue
        lat = sensor.get("lat")
        lon = sensor.get("lon")
        if lat is None or lon is None:
            continue
        traffic_index = min(max(float(payload.get("num_devices_sniffed") or 0.0) / 80.0, 0.0), 1.0)
        for raw_name, pollutant in POLLUTANT_FIELDS.items():
            value = pd.to_numeric(payload.get(raw_name), errors="coerce")
            if pd.isna(value):
                continue
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
                    "base_value": round(float(value), 3),
                    "estimated_value": round(float(value), 3),
                    "temperature": pd.to_numeric(payload.get("temperatura"), errors="coerce"),
                    "humidity": pd.to_numeric(payload.get("umidita"), errors="coerce"),
                    "num_devices_sniffed": int(payload.get("num_devices_sniffed") or 0),
                    "traffic_index": round(float(traffic_index), 3),
                    "green_index": 0.0,
                    "wind_speed_10m": 0.0,
                    "precipitation": 0.0,
                    "traffic_component": 0.0,
                    "green_component": 0.0,
                    "station_count": 1,
                    "nearest_station_km": 0.0,
                    "mean_station_distance_km": 0.0,
                    "uncertainty_score": 0.0,
                    "confidence_label": "alta",
                    "source": SOURCE_NAME,
                    "source_url": SOURCE_URL,
                    "downloaded_at": ingested_at,
                    "is_real": True,
                }
            )
    observations = pd.DataFrame(rows)
    if not observations.empty:
        observations = observations.sort_values(["timestamp", "sensor_id", "pollutant"]).reset_index(drop=True)
    return observations


def build_realtime_dataset(settings: Settings) -> pd.DataFrame:
    sensors = write_real_sensor_geojson(settings)
    observations = normalize_mqtt_observations(settings)
    write_table(observations, settings.processed_dir / "real_sensor_observations.parquet")
    write_table(observations, settings.processed_dir / "campus_air_quality_estimates.parquet")
    metadata = {
        "rows": int(len(observations)),
        "sensors": int(len(sensors)),
        "source": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "generated_at": utc_now_iso(),
        "pollutants": sorted(observations["pollutant"].dropna().unique()) if not observations.empty else [],
    }
    output = settings.processed_dir / "realtime_ingestion_summary.json"
    ensure_dir(output.parent)
    output.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
    return observations


def collect_mqtt_messages(settings: Settings, duration_seconds: int = 60, max_messages: int | None = None) -> int:
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise RuntimeError("Install paho-mqtt to collect live MQTT messages.") from exc

    broker = settings.live_sensors.get("broker", {})
    host = os.environ.get(broker.get("host_env", "UNISA_MQTT_HOST"))
    port_value = os.environ.get(broker.get("port_env", "UNISA_MQTT_PORT"))
    topic = os.environ.get(broker.get("topic_env", "UNISA_MQTT_TOPIC"))
    username = os.environ.get(broker.get("username_env", "UNISA_MQTT_USERNAME"))
    password = os.environ.get(broker.get("password_env", "UNISA_MQTT_PASSWORD"))
    if not host or not port_value or not topic or not username or not password:
        raise RuntimeError(
            "Missing MQTT connection settings. Set UNISA_MQTT_HOST, UNISA_MQTT_PORT, "
            "UNISA_MQTT_TOPIC, UNISA_MQTT_USERNAME, and UNISA_MQTT_PASSWORD."
        )
    port = int(port_value)

    jsonl_path = _configured_path(settings, "mqtt_jsonl_path")
    csv_path = _configured_path(settings, "mqtt_csv_path")
    ensure_dir(jsonl_path.parent)
    ensure_dir(csv_path.parent)

    count = 0

    def on_connect(client: mqtt.Client, userdata: Any, flags: dict[str, Any], reason_code: int, properties: Any = None) -> None:
        client.subscribe(topic)

    def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        nonlocal count
        received_at = pd.Timestamp.utcnow().tz_convert(settings.project.get("timezone", "Europe/Rome")).tz_localize(None)
        row = {
            "timestamp": received_at.isoformat(),
            "topic": message.topic,
            "payload": message.payload.decode("utf-8", errors="replace"),
        }
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp", "topic", "payload"])
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        count += 1
        if max_messages is not None and count >= max_messages:
            client.disconnect()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=30)
    client.loop_start()
    deadline = time.time() + max(1, duration_seconds)
    try:
        while time.time() < deadline and (max_messages is None or count < max_messages):
            time.sleep(0.2)
    finally:
        client.loop_stop()
        client.disconnect()
    return count
