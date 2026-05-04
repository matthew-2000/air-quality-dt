from __future__ import annotations

from typing import Any

import pandas as pd

from unisa_air_twin.data_quality import annotate_quality, quality_summary
from unisa_air_twin.gis import color_zone_geojson


def _zone_features(zone_geojson: dict[str, Any]) -> list[dict[str, Any]]:
    return zone_geojson.get("features", []) if isinstance(zone_geojson, dict) else []


def _point_zone(lat: Any, lon: Any, zone_geojson: dict[str, Any]) -> str:
    lat_value = pd.to_numeric(lat, errors="coerce")
    lon_value = pd.to_numeric(lon, errors="coerce")
    if pd.isna(lat_value) or pd.isna(lon_value):
        return "campus"
    nearest_zone = "campus"
    nearest_distance = float("inf")
    for feature in _zone_features(zone_geojson):
        props = feature.get("properties") or {}
        ring = ((feature.get("geometry") or {}).get("coordinates") or [[]])[0]
        if not ring:
            continue
        lons = [point[0] for point in ring]
        lats = [point[1] for point in ring]
        zone = str(props.get("zone") or "campus")
        if min(lats) <= float(lat_value) <= max(lats) and min(lons) <= float(lon_value) <= max(lons):
            return zone
        center_lat = float(props.get("center_lat", sum(lats) / len(lats)))
        center_lon = float(props.get("center_lon", sum(lons) / len(lons)))
        distance = (center_lat - float(lat_value)) ** 2 + (center_lon - float(lon_value)) ** 2
        if distance < nearest_distance:
            nearest_zone = zone
            nearest_distance = distance
    return nearest_zone


def attach_zones(frame: pd.DataFrame, zone_geojson: dict[str, Any]) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    output = frame.copy()
    output["zone"] = [
        _point_zone(row.get("lat"), row.get("lon"), zone_geojson)
        for row in output.to_dict(orient="records")
    ]
    return output


def zone_summary(snapshot: pd.DataFrame, zone_geojson: dict[str, Any]) -> pd.DataFrame:
    if snapshot.empty:
        return pd.DataFrame(
            columns=[
                "zone",
                "zone_name",
                "mean_value",
                "max_value",
                "min_value",
                "sensors",
                "quality_ok_ratio",
                "traffic_sensitivity",
                "green_capacity",
            ]
        )
    frame = attach_zones(snapshot, zone_geojson)
    frame = annotate_quality(frame)
    grouped = (
        frame.groupby("zone", as_index=False)
        .agg(
            mean_value=("estimated_value", "mean"),
            max_value=("estimated_value", "max"),
            min_value=("estimated_value", "min"),
            sensors=("sensor_id", "nunique"),
            quality_ok_ratio=("quality_label", lambda values: round(float(pd.Series(values).eq("ok").mean()), 3)),
        )
        .round(3)
    )
    zone_props = {
        str((feature.get("properties") or {}).get("zone")): feature.get("properties") or {}
        for feature in _zone_features(zone_geojson)
    }
    grouped["zone_name"] = grouped["zone"].map(lambda zone: zone_props.get(str(zone), {}).get("name", zone))
    grouped["traffic_sensitivity"] = grouped["zone"].map(lambda zone: zone_props.get(str(zone), {}).get("traffic_sensitivity"))
    grouped["green_capacity"] = grouped["zone"].map(lambda zone: zone_props.get(str(zone), {}).get("green_capacity"))
    return grouped.sort_values(["mean_value", "zone"], ascending=[False, True]).reset_index(drop=True)


def colored_zone_geojson(zone_geojson: dict[str, Any], summary: pd.DataFrame) -> dict[str, Any]:
    return color_zone_geojson(zone_geojson, summary, "mean_value")


def pollutant_trend(observations: pd.DataFrame, pollutant: str, limit: int = 36) -> list[dict[str, Any]]:
    if observations.empty:
        return []
    frame = observations[observations["pollutant"] == pollutant].copy()
    if frame.empty:
        return []
    frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
    frame = frame.dropna(subset=["timestamp"])
    if frame.empty:
        return []
    trend = (
        frame.groupby(frame["timestamp"].dt.floor("min"))
        .agg(
            mean_value=("estimated_value", "mean"),
            max_value=("estimated_value", "max"),
            min_value=("estimated_value", "min"),
            sensors=("sensor_id", "nunique"),
        )
        .reset_index(names="timestamp")
        .sort_values("timestamp")
        .tail(limit)
    )
    for column in ["mean_value", "max_value", "min_value"]:
        trend[column] = trend[column].round(3)
    trend["timestamp"] = trend["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%S")
    return trend.to_dict(orient="records")


def analytics_payload(
    observations: pd.DataFrame,
    estimates: pd.DataFrame,
    zone_geojson: dict[str, Any],
    pollutant: str,
    timestamp: str | pd.Timestamp | None,
) -> dict[str, Any]:
    selected_timestamp = pd.Timestamp(timestamp) if timestamp else None
    selected = estimates[estimates["pollutant"] == pollutant].copy() if not estimates.empty else pd.DataFrame()
    if selected_timestamp is not None and not selected.empty:
        selected = selected[selected["timestamp"] == selected_timestamp].copy()
    elif not selected.empty:
        latest = pd.to_datetime(selected["timestamp"], errors="coerce").max()
        selected = selected[selected["timestamp"] == latest].copy()
        selected_timestamp = pd.Timestamp(latest)

    annotated_observations = annotate_quality(observations[observations["pollutant"] == pollutant].copy()) if not observations.empty else pd.DataFrame()
    zones = zone_summary(selected, zone_geojson)
    return {
        "pollutant": pollutant,
        "timestamp": selected_timestamp.strftime("%Y-%m-%dT%H:%M:%S") if selected_timestamp is not None and pd.notna(selected_timestamp) else None,
        "quality": quality_summary(annotated_observations),
        "zone_summary": zones.to_dict(orient="records"),
        "zone_geojson": colored_zone_geojson(zone_geojson, zones),
        "trend": pollutant_trend(observations, pollutant),
    }
