from __future__ import annotations

import json

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.storage import geojson_points_to_frame
from unisa_air_twin.utils import ensure_dir, utc_now_iso

ZONE_DEFINITIONS = [
    {
        "zone_id": "UNISA_ZONE_MOBILITA",
        "zone": "mobilita",
        "name": "Mobilità",
        "center_offset": (-0.0032, -0.0042),
        "half_size": (0.0032, 0.0024),
        "traffic_sensitivity": 0.95,
        "green_capacity": 0.20,
        "description": "Terminal bus, assi di accesso e aree a maggiore pressione di mobilità.",
    },
    {
        "zone_id": "UNISA_ZONE_PARCHEGGIO",
        "zone": "parcheggio",
        "name": "Parcheggi",
        "center_offset": (-0.0060, -0.0052),
        "half_size": (0.0026, 0.0021),
        "traffic_sensitivity": 0.85,
        "green_capacity": 0.35,
        "description": "Aree parcheggio e spazi potenzialmente trasformabili con misure green.",
    },
    {
        "zone_id": "UNISA_ZONE_DIDATTICA",
        "zone": "didattica",
        "name": "Didattica",
        "center_offset": (0.0024, 0.0015),
        "half_size": (0.0034, 0.0025),
        "traffic_sensitivity": 0.45,
        "green_capacity": 0.45,
        "description": "Edifici didattici e flussi pedonali legati alle lezioni.",
    },
    {
        "zone_id": "UNISA_ZONE_SERVIZI",
        "zone": "servizi",
        "name": "Servizi",
        "center_offset": (0.0000, -0.0026),
        "half_size": (0.0028, 0.0021),
        "traffic_sensitivity": 0.55,
        "green_capacity": 0.35,
        "description": "Mensa, servizi agli studenti e spazi di permanenza.",
    },
    {
        "zone_id": "UNISA_ZONE_STUDIO",
        "zone": "studio",
        "name": "Studio",
        "center_offset": (0.0038, 0.0026),
        "half_size": (0.0025, 0.0020),
        "traffic_sensitivity": 0.35,
        "green_capacity": 0.50,
        "description": "Biblioteca scientifica e aree studio.",
    },
    {
        "zone_id": "UNISA_ZONE_VERDE",
        "zone": "verde",
        "name": "Verde",
        "center_offset": (0.0054, 0.0034),
        "half_size": (0.0031, 0.0025),
        "traffic_sensitivity": 0.20,
        "green_capacity": 0.90,
        "description": "Area verde centrale e spazi aperti.",
    },
    {
        "zone_id": "UNISA_ZONE_AMMINISTRAZIONE",
        "zone": "amministrazione",
        "name": "Amministrazione",
        "center_offset": (0.0010, -0.0010),
        "half_size": (0.0022, 0.0018),
        "traffic_sensitivity": 0.40,
        "green_capacity": 0.40,
        "description": "Rettorato e funzioni amministrative.",
    },
]


def _rectangle(lon: float, lat: float, half_lon: float, half_lat: float) -> list[list[float]]:
    return [
        [lon - half_lon, lat - half_lat],
        [lon + half_lon, lat - half_lat],
        [lon + half_lon, lat + half_lat],
        [lon - half_lon, lat + half_lat],
        [lon - half_lon, lat - half_lat],
    ]


def create_campus_zones(settings: Settings) -> pd.DataFrame:
    lat0 = float(settings.campus["fallback_latitude"])
    lon0 = float(settings.campus["fallback_longitude"])
    downloaded_at = utc_now_iso()
    rows: list[dict] = []
    features: list[dict] = []
    for definition in ZONE_DEFINITIONS:
        lon_offset, lat_offset = definition["center_offset"]
        half_lon, half_lat = definition["half_size"]
        center_lon = lon0 + lon_offset
        center_lat = lat0 + lat_offset
        properties = {
            "zone_id": definition["zone_id"],
            "zone": definition["zone"],
            "name": definition["name"],
            "type": "CampusZone",
            "center_lat": center_lat,
            "center_lon": center_lon,
            "traffic_sensitivity": definition["traffic_sensitivity"],
            "green_capacity": definition["green_capacity"],
            "description": definition["description"],
            "coordinate_quality": "derived",
            "source": "manual_campus_reference",
            "source_url": "https://web.unisa.it/vivere-il-campus/unisa-experience/campus-map",
            "downloaded_at": downloaded_at,
            "is_real": True,
        }
        rows.append(properties)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Polygon", "coordinates": [_rectangle(center_lon, center_lat, half_lon, half_lat)]},
                "properties": properties,
            }
        )
    output = settings.processed_dir / "campus_zones.geojson"
    ensure_dir(output.parent)
    output.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return pd.DataFrame(rows)


def create_digital_twin_entities(settings: Settings) -> dict:
    zones_path = settings.processed_dir / "campus_zones.geojson"
    sensors_path = settings.processed_dir / "campus_real_sensors.geojson"
    if not zones_path.exists():
        create_campus_zones(settings)
    zones = json.loads(zones_path.read_text(encoding="utf-8"))
    sensors = geojson_points_to_frame(sensors_path)
    entities: list[dict] = []
    for feature in zones.get("features", []):
        props = feature.get("properties", {})
        entities.append(
            {
                "id": props.get("zone_id"),
                "type": "CampusZone",
                "name": props.get("name"),
                "zone": props.get("zone"),
                "geometry": feature.get("geometry"),
                "properties": {
                    "traffic_sensitivity": props.get("traffic_sensitivity"),
                    "green_capacity": props.get("green_capacity"),
                    "coordinate_quality": props.get("coordinate_quality"),
                    "description": props.get("description"),
                },
            }
        )
    for _, sensor in sensors.iterrows():
        entities.append(
            {
                "id": sensor["sensor_id"],
                "type": "RealSensor",
                "name": sensor["name"],
                "zone": sensor["zone"],
                "geometry": {"type": "Point", "coordinates": [sensor["lon"], sensor["lat"]]},
                "properties": {
                    "coordinate_quality": sensor.get("coordinate_quality", "measured"),
                    "description": sensor.get("description", ""),
                },
            }
        )
    payload = {
        "context": "UNISA Air Quality Digital Twin MVP",
        "generated_at": utc_now_iso(),
        "entities": entities,
        "disclaimer": "Misure reali da sensori UNISA: non è un servizio ufficiale sanitario o regolatorio.",
    }
    output = settings.processed_dir / "digital_twin_entities.json"
    ensure_dir(output.parent)
    output.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return payload


def ensure_twin_layers(settings: Settings) -> None:
    create_campus_zones(settings)
    create_digital_twin_entities(settings)
