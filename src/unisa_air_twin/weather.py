from __future__ import annotations

import re

import pandas as pd
import requests
from bs4 import BeautifulSoup

from unisa_air_twin.config import Settings
from unisa_air_twin.logging_utils import get_logger
from unisa_air_twin.utils import safe_to_parquet, utc_now_iso, write_json

LOGGER = get_logger(__name__)


def inspect_unisa_weather_page(settings: Settings) -> dict:
    url = settings.weather["unisa_page_url"]
    result = {"url": url, "status": "not_checked", "candidate_endpoints": []}
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
    except Exception as exc:
        result["status"] = f"failed: {exc}"
        return result
    soup = BeautifulSoup(response.text, "html.parser")
    candidates: set[str] = set()
    for script in soup.find_all("script"):
        text = script.get("src") or script.get_text(" ", strip=True)
        for match in re.findall(r"https?://[^'\"\s]+|/[^'\"\s]+\.(?:json|csv|php|asp|aspx)", text):
            if any(token in match.lower() for token in ["meteo", "weather", "stazione"]):
                candidates.add(requests.compat.urljoin(url, match))
    result["status"] = "checked"
    result["candidate_endpoints"] = sorted(candidates)
    return result


def _download_open_meteo(settings: Settings) -> pd.DataFrame:
    campus = settings.campus
    params = {
        "latitude": campus["fallback_latitude"],
        "longitude": campus["fallback_longitude"],
        "hourly": ",".join(settings.weather["hourly_variables"]),
        "past_days": 7,
        "forecast_days": 1,
        "timezone": settings.project["timezone"],
    }
    response = requests.get(settings.weather["open_meteo_url"], params=params, timeout=30)
    response.raise_for_status()
    payload = response.json()
    hourly = payload.get("hourly") or {}
    if "time" not in hourly:
        raise ValueError("Open-Meteo response does not contain hourly time series.")
    df = pd.DataFrame(hourly).rename(columns={"time": "timestamp"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df["source"] = "open_meteo_fallback"
    df["source_url"] = response.url
    df["downloaded_at"] = utc_now_iso()
    df["is_synthetic"] = False
    return df.dropna(subset=["timestamp"])


def synthetic_weather(settings: Settings) -> pd.DataFrame:
    timestamps = pd.date_range(end=pd.Timestamp.now().floor("h"), periods=192, freq="h")
    rows = []
    for timestamp in timestamps:
        hour = timestamp.hour
        rows.append(
            {
                "timestamp": timestamp,
                "temperature_2m": 16 + max(0, 12 - abs(hour - 14)) * 0.6,
                "relative_humidity_2m": 72 - max(0, 12 - abs(hour - 14)) * 1.5,
                "precipitation": 0.8 if timestamp.hour in {2, 3} and timestamp.day % 5 == 0 else 0.0,
                "wind_speed_10m": 2.5 + (hour % 6) * 0.25,
                "wind_direction_10m": 180,
                "source": "synthetic_fallback",
                "source_url": settings.weather["unisa_page_url"],
                "downloaded_at": utc_now_iso(),
                "is_synthetic": True,
            }
        )
    return pd.DataFrame(rows)


def download_weather(settings: Settings, force: bool = False) -> pd.DataFrame:
    output = settings.processed_dir / "weather_hourly.parquet"
    if output.exists() and not force:
        LOGGER.info("Using cached weather data %s", output)
        return pd.read_parquet(output)
    inspection = inspect_unisa_weather_page(settings)
    write_json(settings.processed_dir / "unisa_weather_inspection.json", inspection)
    try:
        weather = _download_open_meteo(settings)
        LOGGER.info("Downloaded Open-Meteo fallback weather data for Fisciano/UNISA.")
    except Exception as exc:
        LOGGER.warning("Open-Meteo weather fallback failed: %s", exc)
        weather = synthetic_weather(settings)
    safe_to_parquet(weather, output)
    return weather
