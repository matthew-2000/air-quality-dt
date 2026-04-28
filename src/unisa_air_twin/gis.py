from __future__ import annotations

import pandas as pd

from unisa_air_twin.model import haversine_km, idw_interpolation

VALUE_PALETTES = {
    "value": [[45, 132, 95, 150], [240, 178, 65, 165], [200, 73, 61, 180]],
    "delta": [[42, 145, 95, 170], [232, 232, 220, 90], [196, 72, 68, 175]],
}


def value_color(value: float, low: float, high: float, palette: str = "value") -> list[int]:
    colors = VALUE_PALETTES.get(palette, VALUE_PALETTES["value"])
    span = high - low or 1.0
    ratio = min(max((float(value) - low) / span, 0.0), 1.0)
    left, right = (colors[0], colors[1]) if ratio <= 0.5 else (colors[1], colors[2])
    local_ratio = ratio * 2 if ratio <= 0.5 else (ratio - 0.5) * 2
    return [
        int(left[channel] + (right[channel] - left[channel]) * local_ratio)
        for channel in range(4)
    ]


def build_interpolation_grid(
    sensor_values: pd.DataFrame,
    value_column: str = "estimated_value",
    resolution: int = 24,
    padding_degrees: float = 0.003,
    idw_power: float = 2.0,
) -> pd.DataFrame:
    required = {"lat", "lon", value_column}
    if sensor_values.empty or not required.issubset(sensor_values.columns):
        return pd.DataFrame()
    source = sensor_values.dropna(subset=["lat", "lon", value_column]).copy()
    if source.empty:
        return pd.DataFrame()

    min_lat = float(source["lat"].min()) - padding_degrees
    max_lat = float(source["lat"].max()) + padding_degrees
    min_lon = float(source["lon"].min()) - padding_degrees
    max_lon = float(source["lon"].max()) + padding_degrees
    lat_step = (max_lat - min_lat) / resolution
    lon_step = (max_lon - min_lon) / resolution

    rows: list[dict] = []
    values = source[value_column].astype(float).tolist()
    for lat_index in range(resolution):
        for lon_index in range(resolution):
            south = min_lat + lat_step * lat_index
            north = south + lat_step
            west = min_lon + lon_step * lon_index
            east = west + lon_step
            center_lat = (south + north) / 2
            center_lon = (west + east) / 2
            distances = [
                haversine_km(center_lat, center_lon, float(row["lat"]), float(row["lon"]))
                for _, row in source.iterrows()
            ]
            value = idw_interpolation(values, distances, power=idw_power)
            rows.append(
                {
                    "lat": center_lat,
                    "lon": center_lon,
                    value_column: round(float(value), 3),
                    "polygon": [
                        [west, south],
                        [east, south],
                        [east, north],
                        [west, north],
                    ],
                }
            )
    grid = pd.DataFrame(rows)
    low = float(grid[value_column].min())
    high = float(grid[value_column].max())
    palette = "delta" if "delta" in value_column else "value"
    grid["color"] = [value_color(value, low, high, palette=palette) for value in grid[value_column]]
    return grid


def sensor_snapshot(estimates: pd.DataFrame, pollutant: str, timestamp: pd.Timestamp) -> pd.DataFrame:
    if estimates.empty:
        return pd.DataFrame()
    df = estimates.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    selected_ts = pd.Timestamp(timestamp)
    return df[(df["pollutant"] == pollutant) & (df["timestamp"] == selected_ts)].copy()


def available_timestamps(estimates: pd.DataFrame, pollutant: str) -> list[pd.Timestamp]:
    if estimates.empty:
        return []
    df = estimates[estimates["pollutant"] == pollutant].copy()
    if df.empty:
        return []
    return sorted(pd.to_datetime(df["timestamp"], errors="coerce").dropna().unique())

