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


def build_reliability_grid(
    sensor_values: pd.DataFrame,
    resolution: int = 24,
    padding_degrees: float = 0.003,
) -> pd.DataFrame:
    required = {"lat", "lon"}
    if sensor_values.empty or not required.issubset(sensor_values.columns):
        return pd.DataFrame()
    source = sensor_values.dropna(subset=["lat", "lon"]).copy()
    if source.empty:
        return pd.DataFrame()

    min_lat = float(source["lat"].min()) - padding_degrees
    max_lat = float(source["lat"].max()) + padding_degrees
    min_lon = float(source["lon"].min()) - padding_degrees
    max_lon = float(source["lon"].max()) + padding_degrees
    lat_step = (max_lat - min_lat) / resolution
    lon_step = (max_lon - min_lon) / resolution
    rows: list[dict] = []
    for lat_index in range(resolution):
        for lon_index in range(resolution):
            south = min_lat + lat_step * lat_index
            north = south + lat_step
            west = min_lon + lon_step * lon_index
            east = west + lon_step
            center_lat = (south + north) / 2
            center_lon = (west + east) / 2
            nearest_km = min(
                haversine_km(center_lat, center_lon, float(row["lat"]), float(row["lon"]))
                for _, row in source.iterrows()
            )
            reliability = max(0.0, min(1.0, 1 - nearest_km / 1.2))
            rows.append(
                {
                    "lat": center_lat,
                    "lon": center_lon,
                    "nearest_sensor_km": round(float(nearest_km), 3),
                    "reliability": round(float(reliability), 3),
                    "polygon": [
                        [west, south],
                        [east, south],
                        [east, north],
                        [west, north],
                    ],
                }
            )
    grid = pd.DataFrame(rows)
    grid["color"] = [value_color(value, 0.0, 1.0, palette="value") for value in grid["reliability"]]
    return grid


def summarize_by_zone(values: pd.DataFrame, value_column: str = "estimated_value") -> pd.DataFrame:
    required = {"zone", value_column}
    if values.empty or not required.issubset(values.columns):
        return pd.DataFrame()
    summary = (
        values.groupby("zone", as_index=False)
        .agg(
            mean_value=(value_column, "mean"),
            max_value=(value_column, "max"),
            min_value=(value_column, "min"),
            sensors=("sensor_id", "nunique") if "sensor_id" in values.columns else (value_column, "count"),
        )
        .round(3)
    )
    return summary


def zone_delta_summary(scenario_values: pd.DataFrame) -> pd.DataFrame:
    if scenario_values.empty or "delta" not in scenario_values.columns:
        return pd.DataFrame()
    summary = summarize_by_zone(scenario_values, "delta").rename(
        columns={"mean_value": "mean_delta", "max_value": "max_delta", "min_value": "min_delta"}
    )
    return summary


def color_zone_geojson(zone_geojson: dict, zone_values: pd.DataFrame, value_column: str) -> dict:
    if not zone_geojson:
        return zone_geojson
    values = (
        pd.DataFrame()
        if zone_values.empty or value_column not in zone_values.columns
        else zone_values.dropna(subset=[value_column])
    )
    low = float(values[value_column].min()) if not values.empty else 0.0
    high = float(values[value_column].max()) if not values.empty else 1.0
    value_by_zone = {} if values.empty else dict(zip(values["zone"], values[value_column], strict=False))
    output = {"type": "FeatureCollection", "features": []}
    palette = "delta" if "delta" in value_column else "value"
    for feature in zone_geojson.get("features", []):
        copied = dict(feature)
        copied["properties"] = dict(feature.get("properties", {}))
        zone = copied["properties"].get("zone")
        value = value_by_zone.get(zone)
        copied["properties"][value_column] = None if value is None else round(float(value), 3)
        copied["properties"]["fill_color"] = (
            [130, 130, 130, 35] if value is None else value_color(float(value), low, high, palette=palette)
        )
        output["features"].append(copied)
    return output


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


def timestamp_window(
    timestamps: list[pd.Timestamp],
    selected_timestamp: pd.Timestamp,
    window_label: str,
) -> list[pd.Timestamp]:
    if not timestamps:
        return []
    selected = pd.Timestamp(selected_timestamp)
    normalized = [pd.Timestamp(ts) for ts in timestamps]
    if window_label == "Solo ora selezionata":
        return [selected]
    if window_label == "Mattina":
        return [ts for ts in normalized if ts.date() == selected.date() and 8 <= ts.hour <= 10]
    if window_label == "Pranzo":
        return [ts for ts in normalized if ts.date() == selected.date() and 12 <= ts.hour <= 14]
    if window_label == "Pomeriggio":
        return [ts for ts in normalized if ts.date() == selected.date() and 16 <= ts.hour <= 19]
    if window_label == "Giornata intera":
        return [ts for ts in normalized if ts.date() == selected.date()]
    return [selected]


def window_frame(estimates: pd.DataFrame, pollutant: str, timestamps: list[pd.Timestamp]) -> pd.DataFrame:
    if estimates.empty or not timestamps:
        return pd.DataFrame()
    selected = {pd.Timestamp(ts) for ts in timestamps}
    df = estimates.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    return df[(df["pollutant"] == pollutant) & (df["timestamp"].isin(selected))].copy()
