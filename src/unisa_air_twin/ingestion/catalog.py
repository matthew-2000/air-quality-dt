from __future__ import annotations

import json
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.ingestion.runtime import configured_path
from unisa_air_twin.shared.constants import SOURCE_NAME, SOURCE_URL
from unisa_air_twin.storage import write_table
from unisa_air_twin.utils import ensure_dir, utc_now_iso


def load_sensor_catalog(settings: Settings) -> pd.DataFrame:
    metadata_path = configured_path(settings, "sensor_metadata_path")
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
        rows.append(
            {
                "sensor_id": sensor_id,
                "name": f"Sensore {sensor_id[-6:]}",
                "type": "real",
                "lat": float(lat),
                "lon": float(lon),
                "zone": "campus",
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
