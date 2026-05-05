from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx
import pandas as pd
from shapely.geometry import Point, shape
from shapely.geometry.base import BaseGeometry

from unisa_air_twin.config import Settings
from unisa_air_twin.operational_store import read_metadata, write_metadata
from unisa_air_twin.storage import read_geojson
from unisa_air_twin.utils import ensure_dir, project_path, utc_now_iso

OPEN_METEO_WEATHER_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_AIR_QUALITY_URL = "https://air-quality-api.open-meteo.com/v1/air-quality"


@dataclass
class SourceStatus:
    source_id: str
    label: str
    status: str
    source_url: str
    fetched_at: str | None = None
    cache_path: str | None = None
    error: str | None = None


def _source_config(settings: Settings) -> dict[str, Any]:
    return settings.external_sources or {}


def _cache_dir(settings: Settings) -> Path:
    config = _source_config(settings).get("open_meteo", {})
    value = config.get("cache_dir", "data/raw/external")
    path = Path(value)
    return path if path.is_absolute() else project_path(path)


def _timeout_seconds(settings: Settings) -> float:
    config = _source_config(settings).get("open_meteo", {})
    return float(config.get("request_timeout_seconds", 10))


def _max_cache_age_minutes(settings: Settings) -> int:
    config = _source_config(settings).get("open_meteo", {})
    return int(config.get("max_cache_age_minutes", 60))


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _cache_is_fresh(path: Path, max_age_minutes: int) -> bool:
    payload = _read_json(path)
    fetched_at = payload.get("_fetched_at") if payload else None
    if not fetched_at:
        return False
    timestamp = pd.to_datetime(fetched_at, errors="coerce", utc=True)
    if pd.isna(timestamp):
        return False
    age = pd.Timestamp.now(tz="UTC") - pd.Timestamp(timestamp)
    return age.total_seconds() <= max_age_minutes * 60


def _campus_coordinates(settings: Settings) -> tuple[float, float]:
    return (
        float(settings.campus.get("fallback_latitude", 40.771)),
        float(settings.campus.get("fallback_longitude", 14.790)),
    )


def _weather_url(settings: Settings) -> str:
    config = _source_config(settings).get("open_meteo", {})
    latitude, longitude = _campus_coordinates(settings)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(
            config.get(
                "weather_current",
                ["temperature_2m", "relative_humidity_2m", "precipitation", "wind_speed_10m", "wind_direction_10m"],
            )
        ),
        "timezone": settings.project.get("timezone", "Europe/Rome"),
    }
    return f"{config.get('weather_url', OPEN_METEO_WEATHER_URL)}?{urlencode(params)}"


def _air_quality_url(settings: Settings) -> str:
    config = _source_config(settings).get("open_meteo", {})
    latitude, longitude = _campus_coordinates(settings)
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": ",".join(
            config.get(
                "air_quality_current",
                ["pm10", "pm2_5", "nitrogen_dioxide", "ozone", "european_aqi"],
            )
        ),
        "timezone": settings.project.get("timezone", "Europe/Rome"),
    }
    return f"{config.get('air_quality_url', OPEN_METEO_AIR_QUALITY_URL)}?{urlencode(params)}"


def _fetch_or_cache(
    source_id: str,
    label: str,
    url: str,
    cache_path: Path,
    timeout_seconds: float,
    max_cache_age_minutes: int,
    force: bool,
) -> tuple[dict[str, Any] | None, SourceStatus]:
    if cache_path.exists() and not force and _cache_is_fresh(cache_path, max_cache_age_minutes):
        return _read_json(cache_path), SourceStatus(source_id, label, "cached", url, cache_path=str(cache_path))

    try:
        response = httpx.get(url, timeout=timeout_seconds)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise ValueError("Open-Meteo response is not a JSON object")
        fetched_at = utc_now_iso()
        payload["_fetched_at"] = fetched_at
        payload["_source_url"] = url
        _write_json(cache_path, payload)
        return payload, SourceStatus(source_id, label, "live", url, fetched_at=fetched_at, cache_path=str(cache_path))
    except Exception as exc:
        cached = _read_json(cache_path)
        if cached:
            return cached, SourceStatus(source_id, label, "stale_cache", url, cached.get("_fetched_at"), str(cache_path), str(exc))
        return None, SourceStatus(source_id, label, "failed", url, error=str(exc))


def fetch_external_context(settings: Settings, force: bool = False) -> dict[str, Any]:
    weather_path = _cache_dir(settings) / "open_meteo_weather.json"
    air_quality_path = _cache_dir(settings) / "open_meteo_air_quality.json"
    weather, weather_status = _fetch_or_cache(
        "open_meteo_weather",
        "Open-Meteo Weather",
        _weather_url(settings),
        weather_path,
        _timeout_seconds(settings),
        _max_cache_age_minutes(settings),
        force,
    )
    air_quality, air_quality_status = _fetch_or_cache(
        "open_meteo_air_quality",
        "Open-Meteo Air Quality",
        _air_quality_url(settings),
        air_quality_path,
        _timeout_seconds(settings),
        _max_cache_age_minutes(settings),
        force,
    )
    context = _context_from_payloads(weather, air_quality)
    statuses = [asdict(weather_status), asdict(air_quality_status), *_osm_source_status(settings)]
    write_metadata(settings, "source_statuses", statuses)
    write_metadata(settings, "external_context", context)
    return {"context": context, "sources": statuses}


def load_external_context(settings: Settings) -> dict[str, Any]:
    metadata = read_metadata(settings)
    context = metadata.get("external_context")
    if isinstance(context, dict):
        return context
    weather = _read_json(_cache_dir(settings) / "open_meteo_weather.json")
    air_quality = _read_json(_cache_dir(settings) / "open_meteo_air_quality.json")
    return _context_from_payloads(weather, air_quality)


def read_source_statuses(settings: Settings) -> list[dict[str, Any]]:
    metadata = read_metadata(settings)
    statuses = metadata.get("source_statuses")
    if isinstance(statuses, list):
        output = [status for status in statuses if isinstance(status, dict)]
        source_ids = {str(status.get("source_id")) for status in output}
        defaults = [*_open_meteo_cache_status(settings), *_osm_source_status(settings)]
        output.extend(status for status in defaults if status["source_id"] not in source_ids)
        return output
    return [*_open_meteo_cache_status(settings), *_osm_source_status(settings)]


def _context_from_payloads(weather: dict[str, Any] | None, air_quality: dict[str, Any] | None) -> dict[str, Any]:
    weather_current = weather.get("current", {}) if isinstance(weather, dict) else {}
    air_current = air_quality.get("current", {}) if isinstance(air_quality, dict) else {}
    return {
        "weather": {
            "temperature_2m": _number(weather_current.get("temperature_2m")),
            "relative_humidity_2m": _number(weather_current.get("relative_humidity_2m")),
            "precipitation": _number(weather_current.get("precipitation")),
            "wind_speed_10m": _number(weather_current.get("wind_speed_10m")),
            "wind_direction_10m": _number(weather_current.get("wind_direction_10m")),
            "fetched_at": weather.get("_fetched_at") if isinstance(weather, dict) else None,
            "source_url": weather.get("_source_url") if isinstance(weather, dict) else None,
        },
        "air_quality": {
            "pm10": _number(air_current.get("pm10")),
            "pm25": _number(air_current.get("pm2_5")),
            "no2": _number(air_current.get("nitrogen_dioxide")),
            "o3": _number(air_current.get("ozone")),
            "european_aqi": _number(air_current.get("european_aqi")),
            "fetched_at": air_quality.get("_fetched_at") if isinstance(air_quality, dict) else None,
            "source_url": air_quality.get("_source_url") if isinstance(air_quality, dict) else None,
        },
    }


def _number(value: Any) -> float | None:
    parsed = pd.to_numeric(value, errors="coerce")
    return None if pd.isna(parsed) else float(parsed)


def _coefficient(settings: Settings, group: str, pollutant: str) -> float:
    return float(settings.model.get("coefficients", {}).get(group, {}).get(pollutant, 0.0) or 0.0)


def enrich_measurement(
    settings: Settings,
    *,
    pollutant: str,
    base_value: float,
    traffic_index: float,
    green_index: float,
    context: dict[str, Any],
) -> dict[str, Any]:
    weather = context.get("weather", {}) if isinstance(context, dict) else {}
    air_quality = context.get("air_quality", {}) if isinstance(context, dict) else {}
    wind_speed = float(weather.get("wind_speed_10m") or 0.0)
    precipitation = float(weather.get("precipitation") or 0.0)
    background_value = air_quality.get(pollutant)
    traffic_component = _coefficient(settings, "traffic", pollutant) * traffic_index
    green_component = -_coefficient(settings, "green", pollutant) * green_index
    wind_component = _coefficient(settings, "wind", pollutant) * min(wind_speed / 20.0, 1.0)
    rain_component = _coefficient(settings, "rain", pollutant) * min(precipitation / 5.0, 1.0)
    estimated_value = max(0.0, base_value + traffic_component + green_component + wind_component + rain_component)
    uncertainty_score = 0.08
    if background_value is None:
        uncertainty_score += 0.08
    if not weather.get("fetched_at"):
        uncertainty_score += 0.08
    return {
        "estimated_value": round(estimated_value, 3),
        "wind_speed_10m": round(wind_speed, 3),
        "precipitation": round(precipitation, 3),
        "traffic_component": round(traffic_component, 3),
        "green_component": round(green_component, 3),
        "wind_component": round(wind_component, 3),
        "rain_component": round(rain_component, 3),
        "background_value": round(float(background_value), 3) if background_value is not None else None,
        "background_source": air_quality.get("source_url"),
        "uncertainty_score": round(min(uncertainty_score, 1.0), 3),
        "source_url": ";".join(
            value
            for value in [
                "configured_mqtt_broker",
                weather.get("source_url"),
                air_quality.get("source_url"),
            ]
            if value
        ),
    }


def green_index_for_point(settings: Settings, lat: float, lon: float) -> float:
    layer = read_geojson(settings.processed_dir / "campus_green.geojson")
    features = layer.get("features", []) if isinstance(layer, dict) else []
    if not features:
        return 0.0
    point = Point(float(lon), float(lat))
    distances: list[float] = []
    for feature in features:
        geometry_payload = feature.get("geometry") if isinstance(feature, dict) else None
        if not geometry_payload:
            continue
        try:
            geometry: BaseGeometry = shape(geometry_payload)
        except Exception:
            continue
        if geometry.is_empty:
            continue
        if geometry.contains(point):
            return 1.0
        distances.append(float(geometry.distance(point)))
    if not distances:
        return 0.0
    nearest = min(distances)
    if nearest <= 0.0006:
        return 0.75
    if nearest <= 0.0015:
        return 0.45
    if nearest <= 0.003:
        return 0.2
    return 0.05


def _osm_source_status(settings: Settings) -> list[dict[str, Any]]:
    statuses: list[dict[str, Any]] = []
    for source_id, label, filename in [
        ("osm_green", "OpenStreetMap Green", "campus_green.geojson"),
        ("osm_roads", "OpenStreetMap Roads", "campus_roads.geojson"),
        ("osm_buildings", "OpenStreetMap Buildings", "campus_buildings.geojson"),
    ]:
        path = settings.processed_dir / filename
        payload = read_geojson(path)
        count = len(payload.get("features", [])) if isinstance(payload, dict) else 0
        statuses.append(
            asdict(
                SourceStatus(
                    source_id=source_id,
                    label=label,
                    status="available" if count else "missing",
                    source_url="openstreetmap",
                    cache_path=str(path),
                )
            )
            | {"features": count}
        )
    return statuses


def _open_meteo_cache_status(settings: Settings) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_id, label, url, filename in [
        ("open_meteo_weather", "Open-Meteo Weather", _weather_url(settings), "open_meteo_weather.json"),
        ("open_meteo_air_quality", "Open-Meteo Air Quality", _air_quality_url(settings), "open_meteo_air_quality.json"),
    ]:
        path = _cache_dir(settings) / filename
        cached = _read_json(path)
        rows.append(
            asdict(
                SourceStatus(
                    source_id=source_id,
                    label=label,
                    status="cached" if cached else "missing",
                    source_url=url,
                    fetched_at=cached.get("_fetched_at") if cached else None,
                    cache_path=str(path),
                )
            )
        )
    return rows
