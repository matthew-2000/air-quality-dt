from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from unisa_air_twin.utils import safe_read_table, safe_to_parquet


def read_table(path: str | Path) -> pd.DataFrame:
    return safe_read_table(path)


def write_table(df: pd.DataFrame, path: str | Path) -> None:
    safe_to_parquet(df, path)


def read_geojson(path: str | Path) -> dict:
    geojson_path = Path(path)
    if not geojson_path.exists():
        return {"type": "FeatureCollection", "features": []}
    return json.loads(geojson_path.read_text(encoding="utf-8"))


def geojson_points_to_frame(path: str | Path) -> pd.DataFrame:
    rows = []
    for feature in read_geojson(path).get("features", []):
        geometry = feature.get("geometry") or {}
        if geometry.get("type") != "Point":
            continue
        lon, lat = geometry.get("coordinates", [None, None])[:2]
        row = dict(feature.get("properties") or {})
        row["lat"] = lat
        row["lon"] = lon
        rows.append(row)
    return pd.DataFrame(rows)

