from __future__ import annotations

import json
import os

import pandas as pd

from unisa_air_twin.config import load_dotenv, load_settings
from unisa_air_twin.live_sensors import (
    build_operational_snapshots,
    build_realtime_dataset,
    load_sensor_catalog,
)


def test_live_sensors_builds_real_sensor_rows(tmp_path) -> None:
    raw_dir = tmp_path / "raw"
    processed_dir = tmp_path / "processed"
    raw_dir.mkdir()
    processed_dir.mkdir()
    metadata_path = raw_dir / "sensor_catalog.json"
    csv_path = raw_dir / "mqtt_data.csv"
    jsonl_path = raw_dir / "mqtt_raw.jsonl"
    metadata_path.write_text(
        json.dumps([{"ID": "ITTEST123456", "lat": 40.771, "lon": 14.79}]),
        encoding="utf-8",
    )
    csv_path.write_text(
        'timestamp,topic,payload\n'
        '2026-04-29T15:12:53,ITTEST123456,'
        '"{""ID"":""ITTEST123456"",""timestamp"":1777468356,""pm2_5"":1.8,""pm10"":5.02,""pm1"":1.7,""voc_index"":116,""num_devices_sniffed"":8}"\n',
        encoding="utf-8",
    )
    jsonl_path.write_text("", encoding="utf-8")

    settings = load_settings()
    settings.raw_dir = raw_dir
    settings.processed_dir = processed_dir
    settings.live_sensors["raw"] = {
        "sensor_metadata_path": str(metadata_path),
        "mqtt_csv_path": str(csv_path),
        "mqtt_jsonl_path": str(jsonl_path),
    }

    sensors = load_sensor_catalog(settings)
    observations = build_realtime_dataset(settings)

    assert len(sensors) == 1
    assert set(observations["pollutant"]) == {"pm1", "pm25", "pm10", "voc_index"}
    assert observations["is_real"].eq(True).all()
    assert (processed_dir / "campus_real_sensors.geojson").exists()


def test_default_pedt_sensor_catalog_is_versioned() -> None:
    sensors = load_sensor_catalog(load_settings())

    assert len(sensors) == 19
    assert "IT5YELKAH9XRB5" in set(sensors["sensor_id"])
    assert sensors[["lat", "lon"]].notna().all().all()


def test_operational_snapshots_merge_staggered_sensor_messages() -> None:
    settings = load_settings()
    observations = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-04-29 15:12:53"),
                "received_at": pd.Timestamp("2026-04-29 15:12:53"),
                "sensor_id": "A",
                "sensor_name": "Sensore A",
                "lat": 40.771,
                "lon": 14.790,
                "zone": "campus",
                "pollutant": "pm10",
                "base_value": 10.0,
                "estimated_value": 10.0,
                "station_count": 1,
                "confidence_label": "alta",
            },
            {
                "timestamp": pd.Timestamp("2026-04-29 15:12:58"),
                "received_at": pd.Timestamp("2026-04-29 15:12:58"),
                "sensor_id": "B",
                "sensor_name": "Sensore B",
                "lat": 40.772,
                "lon": 14.791,
                "zone": "campus",
                "pollutant": "pm10",
                "base_value": 20.0,
                "estimated_value": 20.0,
                "station_count": 1,
                "confidence_label": "alta",
            },
            {
                "timestamp": pd.Timestamp("2026-04-29 15:13:02"),
                "received_at": pd.Timestamp("2026-04-29 15:13:02"),
                "sensor_id": "A",
                "sensor_name": "Sensore A",
                "lat": 40.771,
                "lon": 14.790,
                "zone": "campus",
                "pollutant": "pm10",
                "base_value": 11.0,
                "estimated_value": 11.0,
                "station_count": 1,
                "confidence_label": "alta",
            },
        ]
    )

    snapshots = build_operational_snapshots(settings, observations)

    latest_snapshot = snapshots[snapshots["timestamp"] == pd.Timestamp("2026-04-29 15:13:00")]
    assert latest_snapshot["sensor_id"].nunique() == 2
    assert latest_snapshot["station_count"].eq(2).all()
    assert latest_snapshot["capable_sensor_count"].eq(2).all()
    assert latest_snapshot["coverage_ratio"].eq(1.0).all()
    assert latest_snapshot.loc[latest_snapshot["sensor_id"] == "B", "reading_age_seconds"].iloc[0] > 60


def test_load_dotenv_populates_missing_environment_variables(tmp_path, monkeypatch) -> None:
    dotenv_path = tmp_path / ".env.local"
    dotenv_path.write_text(
        "UNISA_MQTT_HOST=test-broker\n"
        "export UNISA_MQTT_PORT=1884\n"
        "UNISA_MQTT_USERNAME='user'\n"
        'UNISA_MQTT_PASSWORD="pass"\n'
        'UNISA_MQTT_TOPIC="#"\n',
        encoding="utf-8",
    )

    for key in ["UNISA_MQTT_HOST", "UNISA_MQTT_PORT", "UNISA_MQTT_USERNAME", "UNISA_MQTT_PASSWORD", "UNISA_MQTT_TOPIC"]:
        monkeypatch.delenv(key, raising=False)

    load_dotenv(dotenv_path)

    assert os.environ["UNISA_MQTT_HOST"] == "test-broker"
    assert os.environ["UNISA_MQTT_PORT"] == "1884"
    assert os.environ["UNISA_MQTT_USERNAME"] == "user"
    assert os.environ["UNISA_MQTT_PASSWORD"] == "pass"
    assert os.environ["UNISA_MQTT_TOPIC"] == "#"


def test_load_settings_allows_env_local_to_override_env_file(tmp_path, monkeypatch) -> None:
    settings_path = tmp_path / "settings.yaml"
    settings_path.write_text(
        """
project:
  name: test
paths:
  raw_dir: data/raw
  processed_dir: data/processed
campus:
  fallback_latitude: 40.771
  fallback_longitude: 14.790
live_sensors: {}
model: {}
""",
        encoding="utf-8",
    )
    env_path = tmp_path / ".env"
    local_path = tmp_path / ".env.local"
    env_path.write_text("UNISA_MQTT_HOST=base-host\n", encoding="utf-8")
    local_path.write_text("UNISA_MQTT_HOST=local-host\n", encoding="utf-8")

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("UNISA_MQTT_HOST", raising=False)
    monkeypatch.setattr("unisa_air_twin.config.project_path", lambda *parts: tmp_path.joinpath(*parts))

    load_settings(settings_path)

    assert os.environ["UNISA_MQTT_HOST"] == "local-host"
