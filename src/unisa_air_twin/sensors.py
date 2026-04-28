from __future__ import annotations

import json

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.utils import ensure_dir, utc_now_iso

SENSOR_DEFINITIONS = [
    (
        "UNISA_A1_RETTORATO",
        "Rettorato / area A1",
        0.0010,
        -0.0010,
        "amministrazione",
        "Sensore virtuale presso area rettorato.",
    ),
    (
        "UNISA_EDIFICIO_F",
        "Edificio F",
        0.0022,
        0.0015,
        "didattica",
        "Sensore virtuale presso area didattica Edificio F.",
    ),
    (
        "UNISA_TERMINAL_BUS",
        "Terminal Bus",
        -0.0030,
        -0.0040,
        "mobilita",
        "Sensore virtuale in area terminal bus.",
    ),
    (
        "UNISA_PARCHEGGIO_MULTIPIANO",
        "Parcheggio Multipiano",
        -0.0048,
        -0.0050,
        "parcheggio",
        "Sensore virtuale in prossimita del parcheggio multipiano.",
    ),
    (
        "UNISA_MENSA",
        "Mensa",
        0.0000,
        -0.0025,
        "servizi",
        "Sensore virtuale presso area mensa.",
    ),
    (
        "UNISA_BIBLIOTECA_SCIENTIFICA",
        "Biblioteca Scientifica",
        0.0036,
        0.0024,
        "studio",
        "Sensore virtuale presso biblioteca scientifica.",
    ),
    (
        "UNISA_AREA_VERDE",
        "Area verde centrale",
        0.0050,
        0.0030,
        "verde",
        "Sensore virtuale in area verde del campus.",
    ),
]


def create_virtual_sensors(settings: Settings) -> pd.DataFrame:
    lat0 = settings.campus["fallback_latitude"]
    lon0 = settings.campus["fallback_longitude"]
    downloaded_at = utc_now_iso()
    rows = []
    features = []
    for sensor_id, name, lon_offset, lat_offset, zone, description in SENSOR_DEFINITIONS:
        lat = lat0 + lat_offset
        lon = lon0 + lon_offset
        row = {
            "sensor_id": sensor_id,
            "name": name,
            "type": "virtual",
            "lat": lat,
            "lon": lon,
            "zone": zone,
            "description": description,
            "coordinate_quality": "synthetic",
            "source": "manual_campus_reference",
            "source_url": "https://web.unisa.it/vivere-il-campus/unisa-experience/campus-map",
            "downloaded_at": downloaded_at,
            "is_synthetic": False,
        }
        rows.append(row)
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": row,
            }
        )
    output = settings.processed_dir / "campus_virtual_sensors.geojson"
    ensure_dir(output.parent)
    output.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return pd.DataFrame(rows)

