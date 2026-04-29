from __future__ import annotations

import math

import pandas as pd

from unisa_air_twin.config import Settings


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def traffic_index(timestamp: pd.Timestamp, sensor_id: str | None = None, devices_sniffed: float | None = None) -> float:
    if devices_sniffed is not None and pd.notna(devices_sniffed):
        return round(float(min(max(devices_sniffed / 80.0, 0.0), 1.0)), 3)
    ts = pd.Timestamp(timestamp)
    if ts.weekday() >= 5:
        return 0.2
    if ts.hour in {8, 9, 17, 18}:
        return 1.0
    if 11 <= ts.hour <= 16:
        return 0.55
    if 0 <= ts.hour <= 6 or ts.hour >= 21:
        return 0.15
    return 0.35


def green_index(sensor_id: str) -> float:
    return 0.0


def idw_interpolation(values: list[float], distances_km: list[float], power: float = 2.0) -> float:
    valid = [(float(v), max(float(d), 0.0)) for v, d in zip(values, distances_km, strict=False) if pd.notna(v)]
    if not valid:
        return float("nan")
    for value, distance in valid:
        if distance < 0.001:
            return value
    weights = [1 / (distance**power) for _, distance in valid]
    return sum(value * weight for (value, _), weight in zip(valid, weights, strict=False)) / sum(weights)


def _confidence_label(uncertainty_score: float) -> str:
    if uncertainty_score <= 0.33:
        return "alta"
    if uncertainty_score <= 0.66:
        return "media"
    return "bassa"


def estimate_spatial_uncertainty(
    distances_km: list[float],
    station_count: int,
    radius_km: float = 1.2,
) -> tuple[float, str]:
    usable_distances = [float(distance) for distance in distances_km if pd.notna(distance)]
    if not usable_distances or station_count <= 0:
        return 1.0, "bassa"
    nearest_km = min(usable_distances)
    distance_penalty = min(nearest_km / max(radius_km, 0.1), 1.0)
    density_penalty = max(0.0, 1.0 - min(station_count, 5) / 5)
    score = min(1.0, 0.75 * distance_penalty + 0.25 * density_penalty)
    score = round(float(score), 3)
    return score, _confidence_label(score)


def estimate_campus_air_quality(settings: Settings) -> pd.DataFrame:
    from unisa_air_twin.live_sensors import build_realtime_dataset

    return build_realtime_dataset(settings)
