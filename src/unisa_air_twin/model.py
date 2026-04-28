from __future__ import annotations

import math

import pandas as pd

from unisa_air_twin import arpac
from unisa_air_twin.config import Settings
from unisa_air_twin.sensors import create_virtual_sensors
from unisa_air_twin.storage import geojson_points_to_frame, read_table, write_table
from unisa_air_twin.utils import utc_now_iso, write_schema_report

EXTRA_TRAFFIC_SENSORS = {"UNISA_TERMINAL_BUS", "UNISA_PARCHEGGIO_MULTIPIANO"}
GREEN_INDEX_BY_SENSOR = {
    "UNISA_AREA_VERDE": 1.0,
    "UNISA_BIBLIOTECA_SCIENTIFICA": 0.5,
    "UNISA_A1_RETTORATO": 0.4,
    "UNISA_TERMINAL_BUS": 0.1,
    "UNISA_PARCHEGGIO_MULTIPIANO": 0.05,
    "UNISA_MENSA": 0.3,
    "UNISA_EDIFICIO_F": 0.25,
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def traffic_index(timestamp: pd.Timestamp, sensor_id: str | None = None) -> float:
    ts = pd.Timestamp(timestamp)
    is_weekday = ts.weekday() < 5
    hour = ts.hour
    if not is_weekday:
        base = 0.2
    elif hour in {8, 9, 17, 18}:
        base = 1.0
    elif 11 <= hour <= 16:
        base = 0.55
    elif 0 <= hour <= 6 or hour >= 21:
        base = 0.15
    else:
        base = 0.35
    if sensor_id in EXTRA_TRAFFIC_SENSORS:
        base += 0.15
    return round(float(min(base, 1.0)), 3)


def green_index(sensor_id: str) -> float:
    return GREEN_INDEX_BY_SENSOR.get(sensor_id, 0.25)


def idw_interpolation(values: list[float], distances_km: list[float], power: float = 2.0) -> float:
    valid = [(float(v), max(float(d), 0.0)) for v, d in zip(values, distances_km, strict=False) if pd.notna(v)]
    if not valid:
        return float("nan")
    for value, distance in valid:
        if distance < 0.001:
            return value
    weights = [1 / (distance**power) for _, distance in valid]
    return sum(value * weight for (value, _), weight in zip(valid, weights, strict=False)) / sum(weights)


def _load_sensors(settings: Settings) -> pd.DataFrame:
    sensor_path = settings.processed_dir / "campus_virtual_sensors.geojson"
    sensors = geojson_points_to_frame(sensor_path)
    if sensors.empty:
        sensors = create_virtual_sensors(settings)
    return sensors


def _load_observations(settings: Settings) -> pd.DataFrame:
    observations = read_table(settings.processed_dir / "air_quality_observations.parquet")
    if observations.empty:
        observations = arpac.synthetic_air_quality_observations()
        write_table(observations, settings.processed_dir / "air_quality_observations.parquet")
    observations["timestamp"] = pd.to_datetime(observations["timestamp"], errors="coerce")
    return observations.dropna(subset=["timestamp"])


def _load_station_metadata(settings: Settings) -> pd.DataFrame:
    stations = read_table(settings.processed_dir / "arpac_station_metadata.parquet")
    if stations.empty:
        stations = arpac.clean_station_metadata(settings)
        write_table(stations, settings.processed_dir / "arpac_station_metadata.parquet")
    return stations


def _weather_by_hour(settings: Settings) -> pd.DataFrame:
    weather = read_table(settings.processed_dir / "weather_hourly.parquet")
    if weather.empty:
        return pd.DataFrame(columns=["timestamp", "wind_speed_10m", "precipitation"])
    weather["timestamp"] = pd.to_datetime(weather["timestamp"], errors="coerce").dt.floor("h")
    return weather.dropna(subset=["timestamp"]).drop_duplicates("timestamp").set_index("timestamp")


def _weather_adjustment(pollutant: str, wind_speed: float, precipitation: float, timestamp: pd.Timestamp, settings: Settings) -> float:
    coefficients = settings.model["coefficients"]
    wind_coeff = float(coefficients["wind"].get(pollutant, 0.0))
    rain_coeff = float(coefficients["rain"].get(pollutant, 0.0))
    wind_component = wind_coeff * min(max(wind_speed, 0.0), 10.0) / 10.0
    rain_component = rain_coeff if precipitation > 0 else 0.0
    ozone_sun_component = 1.5 if pollutant == "o3" and 13 <= pd.Timestamp(timestamp).hour <= 17 else 0.0
    return wind_component + rain_component + ozone_sun_component


def _station_observations_with_distances(settings: Settings, observations: pd.DataFrame, stations: pd.DataFrame) -> pd.DataFrame:
    merged = observations.merge(stations[["station_id", "lat", "lon"]], on="station_id", how="left")
    campus_lat = settings.campus["fallback_latitude"]
    campus_lon = settings.campus["fallback_longitude"]
    if merged[["lat", "lon"]].notna().all(axis=1).any():
        merged["distance_to_campus_km"] = merged.apply(
            lambda row: haversine_km(campus_lat, campus_lon, row["lat"], row["lon"])
            if pd.notna(row["lat"]) and pd.notna(row["lon"])
            else float("nan"),
            axis=1,
        )
        radius = float(settings.arpac.get("station_radius_km", 40))
        nearby_ids = set(
            merged.loc[merged["distance_to_campus_km"].le(radius), "station_id"].dropna().astype(str).unique()
        )
        if nearby_ids:
            return merged[merged["station_id"].astype(str).isin(nearby_ids)].copy()
    write_schema_report(
        settings.processed_dir,
        [
            {
                "warning": "No ARPAC stations with usable coordinates inside configured radius; using all available stations or fallback observations.",
                "radius_km": settings.arpac.get("station_radius_km", 40),
            }
        ],
    )
    return merged


def estimate_campus_air_quality(settings: Settings) -> pd.DataFrame:
    sensors = _load_sensors(settings)
    observations = _load_observations(settings)
    stations = _load_station_metadata(settings)
    weather = _weather_by_hour(settings)
    station_obs = _station_observations_with_distances(settings, observations, stations)
    pollutants = [p for p in settings.model["pollutants"] if p in station_obs.columns]
    if not pollutants:
        write_schema_report(
            settings.processed_dir,
            [{"warning": "No configured pollutant columns available. Replacing observations with synthetic fallback."}],
        )
        observations = arpac.synthetic_air_quality_observations()
        station_obs = _station_observations_with_distances(settings, observations, arpac._synthetic_station_metadata())
        pollutants = [p for p in settings.model["pollutants"] if p in station_obs.columns]
    timestamps = sorted(pd.Series(station_obs["timestamp"].dropna().unique()).tail(168))
    rows: list[dict] = []
    coefficients = settings.model["coefficients"]
    for timestamp in timestamps:
        ts = pd.Timestamp(timestamp).floor("h")
        hour_obs = station_obs[station_obs["timestamp"] == timestamp]
        weather_row = weather.loc[ts] if ts in weather.index else {}
        wind_speed = float(getattr(weather_row, "wind_speed_10m", 2.0) if not isinstance(weather_row, dict) else 2.0)
        precipitation = float(getattr(weather_row, "precipitation", 0.0) if not isinstance(weather_row, dict) else 0.0)
        for _, sensor in sensors.iterrows():
            sensor_id = sensor["sensor_id"]
            ti = traffic_index(ts, sensor_id)
            gi = green_index(sensor_id)
            for pollutant in pollutants:
                values = hour_obs[pollutant].tolist()
                if hour_obs[["lat", "lon"]].notna().all(axis=1).any():
                    distances = [
                        haversine_km(float(sensor["lat"]), float(sensor["lon"]), float(row["lat"]), float(row["lon"]))
                        if pd.notna(row["lat"]) and pd.notna(row["lon"])
                        else 20.0
                        for _, row in hour_obs.iterrows()
                    ]
                else:
                    distances = [1.0 for _ in values]
                base_value = idw_interpolation(values, distances, float(settings.model.get("idw_power", 2.0)))
                if pd.isna(base_value):
                    continue
                traffic_component = float(coefficients["traffic"].get(pollutant, 0.0)) * ti
                green_component = float(coefficients["green"].get(pollutant, 0.0)) * gi
                weather_component = _weather_adjustment(pollutant, wind_speed, precipitation, ts, settings)
                estimated_value = max(0.0, base_value + traffic_component - green_component + weather_component)
                is_synthetic = bool(hour_obs.get("is_synthetic", pd.Series([False])).fillna(False).any())
                source = "idw_model_synthetic_fallback" if is_synthetic else "arpac_idw_model"
                rows.append(
                    {
                        "timestamp": ts,
                        "sensor_id": sensor_id,
                        "sensor_name": sensor["name"],
                        "lat": sensor["lat"],
                        "lon": sensor["lon"],
                        "zone": sensor["zone"],
                        "pollutant": pollutant,
                        "base_value": round(float(base_value), 3),
                        "estimated_value": round(float(estimated_value), 3),
                        "traffic_index": ti,
                        "green_index": gi,
                        "wind_speed_10m": wind_speed,
                        "precipitation": precipitation,
                        "traffic_component": round(traffic_component, 3),
                        "green_component": round(green_component, 3),
                        "weather_component": round(weather_component, 3),
                        "source": source,
                        "source_url": "https://dati.arpacampania.it/",
                        "downloaded_at": utc_now_iso(),
                        "is_synthetic": is_synthetic,
                    }
                )
    estimates = pd.DataFrame(rows)
    write_table(estimates, settings.processed_dir / "campus_air_quality_estimates.parquet")
    return estimates
