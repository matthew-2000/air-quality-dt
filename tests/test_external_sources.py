from __future__ import annotations

import json
from pathlib import Path

from unisa_air_twin.config import load_settings
from unisa_air_twin.external_sources import (
    enrich_measurement,
    fetch_external_context,
    green_index_for_point,
)


def _settings(tmp_path: Path):
    settings = load_settings()
    settings.raw_dir = tmp_path / "raw"
    settings.processed_dir = tmp_path / "processed"
    settings.raw_dir.mkdir()
    settings.processed_dir.mkdir()
    settings.external_sources["open_meteo"] = {
        "cache_dir": str(settings.raw_dir / "external"),
        "request_timeout_seconds": 1,
        "max_cache_age_minutes": 60,
    }
    return settings


def test_fetch_external_context_caches_open_meteo_payloads(tmp_path, monkeypatch) -> None:
    settings = _settings(tmp_path)

    class FakeResponse:
        def __init__(self, payload: dict) -> None:
            self._payload = payload

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return self._payload

    def fake_get(url: str, timeout: float) -> FakeResponse:
        assert timeout == 1
        if "air-quality" in url:
            return FakeResponse({"current": {"pm10": 18.0, "pm2_5": 9.0, "nitrogen_dioxide": 22.0}})
        return FakeResponse({"current": {"wind_speed_10m": 12.0, "precipitation": 0.4}})

    monkeypatch.setattr("unisa_air_twin.external_sources.httpx.get", fake_get)

    payload = fetch_external_context(settings, force=True)

    assert payload["context"]["weather"]["wind_speed_10m"] == 12.0
    assert payload["context"]["air_quality"]["pm25"] == 9.0
    assert {source["status"] for source in payload["sources"]} >= {"live", "missing"}
    assert (settings.raw_dir / "external" / "open_meteo_weather.json").exists()


def test_enrichment_uses_weather_background_and_green_layer(tmp_path) -> None:
    settings = _settings(tmp_path)
    (settings.processed_dir / "campus_green.geojson").write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {},
                        "geometry": {
                            "type": "Polygon",
                            "coordinates": [
                                [
                                    [14.789, 40.770],
                                    [14.791, 40.770],
                                    [14.791, 40.772],
                                    [14.789, 40.772],
                                    [14.789, 40.770],
                                ]
                            ],
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    context = {
        "weather": {"wind_speed_10m": 10.0, "precipitation": 0.5, "source_url": "weather"},
        "air_quality": {"pm10": 21.0, "source_url": "air"},
    }

    green_index = green_index_for_point(settings, 40.771, 14.790)
    enriched = enrich_measurement(
        settings,
        pollutant="pm10",
        base_value=30.0,
        traffic_index=0.5,
        green_index=green_index,
        context=context,
    )

    assert green_index == 1.0
    assert enriched["background_value"] == 21.0
    assert enriched["traffic_component"] > 0
    assert enriched["green_component"] < 0
    assert enriched["wind_speed_10m"] == 10.0
