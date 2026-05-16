from __future__ import annotations

import asyncio
import json

import pandas as pd
from fastapi.testclient import TestClient

import api.dependencies as api_deps
import api.main as api_main
import api.routers.jobs as jobs_routes
import api.routers.twin as twin_routes
from unisa_air_twin.config import load_settings


def isolated_settings(tmp_path):
    settings = load_settings()
    settings.raw_dir = tmp_path / "raw"
    settings.processed_dir = tmp_path / "processed"
    settings.raw_dir.mkdir()
    settings.processed_dir.mkdir()
    settings.live_sensors["operational"] = {"db_path": str(settings.processed_dir / "realtime_operational.db")}
    return settings


class FakeTwinService:
    def refresh(self) -> dict:
        return self.summary()

    def summary(self) -> dict:
        return {
            "project": "UNISA Air Quality Digital Twin",
            "source": "UNISA AQDT",
            "campus": {"name": "Campus di Fisciano", "latitude": 40.771, "longitude": 14.79},
            "pollutants": [],
            "default_pollutant": "pm10",
            "latest_timestamp": None,
            "latest_received_at": None,
            "rows": 0,
            "raw_rows": 0,
            "raw_message_rows": 0,
            "observation_rows": 0,
            "snapshot_rows": 0,
            "sensors": 1,
            "active_sensors": 0,
            "capable_sensors": 0,
            "coverage_ratio": 0.0,
            "sensor_health": [
                {
                    "sensor_id": "A",
                    "sensor_name": "Sensore A",
                    "status": "silent",
                    "latest_received_at": None,
                    "latest_measured_at": None,
                    "pollutants": [],
                }
            ],
            "stations": 0,
            "coverage_by_pollutant": [],
            "layer_counts": {},
            "ingestion": {"raw_rows": 0, "raw_message_rows": 0, "observation_rows": 0, "snapshot_rows": 0, "sensors": 1},
            "live_feed": {"status": "unknown", "configured": True, "missing_env": [], "latest_received_at": None, "age_minutes": None},
            "warnings": [],
            "mode": "real_only",
        }

    def timestamps(self, pollutant: str) -> list[str]:
        return []

    def analytics(self, pollutant: str, timestamp: str | None = None) -> dict:
        return {
            "pollutant": pollutant,
            "timestamp": timestamp,
            "quality": {"rows": 0, "ok_rows": 0, "watch_rows": 0, "critical_rows": 0, "ok_ratio": 0.0, "flags": []},
            "zone_summary": [],
            "zone_geojson": {"type": "FeatureCollection", "features": []},
            "trend": [],
        }

    def load(self) -> dict:
        return {
            "observations": pd.DataFrame(
                [
                    {
                        "timestamp": "2026-01-01T10:00:00",
                        "sensor_id": "A",
                        "sensor_name": "Sensore A",
                        "pollutant": "pm10",
                        "estimated_value": 10.0,
                    },
                    {
                        "timestamp": "2026-01-01T10:01:00",
                        "sensor_id": "A",
                        "sensor_name": "Sensore A",
                        "pollutant": "pm10",
                        "estimated_value": 12.0,
                    },
                ]
            ),
            "layers": {"zones": {"type": "FeatureCollection", "features": []}},
            "sensors": pd.DataFrame([{"sensor_id": "A", "name": "Sensore A", "lat": 40.771, "lon": 14.79, "zone": "campus"}]),
        }

    def snapshot(self, pollutant: str, timestamp: str) -> pd.DataFrame:
        return pd.DataFrame(
            [
                {
                    "timestamp": timestamp,
                    "sensor_id": "A",
                    "sensor_name": "Sensore A",
                    "pollutant": pollutant,
                    "estimated_value": 12.0,
                    "reading_age_seconds": 30,
                    "coverage_ratio": 1.0,
                    "lat": 40.771,
                    "lon": 14.79,
                }
            ]
        )


def test_summary_contract_exposes_raw_and_observation_counts(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "get_twin_service", lambda: FakeTwinService())
    client = TestClient(api_main.app)

    response = client.get("/api/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_message_rows"] == 0
    assert payload["observation_rows"] == 0
    assert payload["sensor_health"][0]["status"] == "silent"


def test_timestamps_contract(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "get_twin_service", lambda: FakeTwinService())
    client = TestClient(api_main.app)

    response = client.get("/api/timestamps?pollutant=pm10")

    assert response.status_code == 200
    assert response.json() == {"timestamps": []}


def test_analytics_contract(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "get_twin_service", lambda: FakeTwinService())
    client = TestClient(api_main.app)

    response = client.get("/api/analytics?pollutant=pm10")

    assert response.status_code == 200
    assert response.json()["quality"]["rows"] == 0


def test_stream_emits_connected_event(monkeypatch) -> None:
    monkeypatch.setattr(api_deps, "get_twin_service", lambda: FakeTwinService())

    class FakeRequest:
        async def is_disconnected(self) -> bool:
            return False

    async def collect_first_event() -> str:
        stream = twin_routes._summary_stream(FakeRequest())
        try:
            return await anext(stream)
        finally:
            await stream.aclose()

    chunk = asyncio.run(collect_first_event())
    lines = [line for line in chunk.splitlines() if line]

    assert "event: connected" in lines
    data_line = next(line for line in lines if line.startswith("data: "))
    payload = json.loads(data_line.removeprefix("data: "))
    assert payload["snapshot_rows"] == 0
    assert payload["live_feed_status"] == "unknown"


def test_refresh_job_contract(monkeypatch, tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    monkeypatch.setattr(api_deps, "get_settings", lambda: settings)
    monkeypatch.setattr(api_deps, "get_twin_service", lambda: FakeTwinService())
    monkeypatch.setattr(jobs_routes, "refresh_operational_snapshots", lambda _settings: {"snapshot_rows": 3})
    client = TestClient(api_main.app)

    response = client.post("/api/jobs/refresh")

    assert response.status_code == 202
    payload = response.json()
    assert payload["name"] == "refresh_snapshots"
    assert payload["status"] in {"queued", "running", "completed"}

    detail = client.get(f"/api/jobs/{payload['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["result"].get("snapshot_rows") == 3


def test_live_ingest_job_contract(monkeypatch, tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    monkeypatch.setattr(api_deps, "get_settings", lambda: settings)
    monkeypatch.setattr(api_deps, "get_twin_service", lambda: FakeTwinService())
    monkeypatch.setattr(
        jobs_routes,
        "collect_live_once",
        lambda _settings, duration_seconds, max_messages: {
            "mqtt_messages": max_messages,
            "snapshot_rows": duration_seconds,
        },
    )
    client = TestClient(api_main.app)

    response = client.post("/api/jobs/live-ingest?duration_seconds=7&max_messages=9")

    assert response.status_code == 202
    payload = response.json()
    assert payload["name"] == "live_ingest_once"
    assert payload["status"] in {"queued", "running", "completed"}

    detail = client.get(f"/api/jobs/{payload['job_id']}")
    assert detail.status_code == 200
    assert detail.json()["result"] == {"mqtt_messages": 9, "snapshot_rows": 7}


def test_export_observations_contract(monkeypatch) -> None:
    monkeypatch.setattr(
        twin_routes,
        "read_observations",
        lambda _settings: pd.DataFrame([{"sensor_id": "A", "pollutant": "pm10", "estimated_value": 12.5}]),
    )
    client = TestClient(api_main.app)

    response = client.get("/api/export/observations?format=csv")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "sensor_id,pollutant,estimated_value" in response.text


def test_sources_contract(monkeypatch) -> None:
    monkeypatch.setattr(twin_routes, "read_source_statuses", lambda _settings: [{"source_id": "osm_green", "status": "available"}])
    client = TestClient(api_main.app)

    response = client.get("/api/sources")

    assert response.status_code == 200
    assert response.json()["sources"][0]["source_id"] == "osm_green"


def test_frontend_routes_serve_built_assets(monkeypatch, tmp_path) -> None:
    dist_dir = tmp_path / "dist"
    assets_dir = dist_dir / "assets"
    assets_dir.mkdir(parents=True)
    index_path = dist_dir / "index.html"
    asset_path = assets_dir / "main.js"
    index_path.write_text("<html><body>demo app</body></html>", encoding="utf-8")
    asset_path.write_text("console.log('demo')", encoding="utf-8")

    monkeypatch.setattr(api_deps, "frontend_dist_dir", lambda: dist_dir)
    monkeypatch.setattr(api_deps, "frontend_index_path", lambda: index_path)
    client = TestClient(api_main.app)

    root_response = client.get("/")
    assert root_response.status_code == 200
    assert "demo app" in root_response.text

    asset_response = client.get("/assets/main.js")
    assert asset_response.status_code == 200
    assert "console.log('demo')" in asset_response.text

    spa_response = client.get("/dashboard")
    assert spa_response.status_code == 200
    assert "demo app" in spa_response.text


def test_health_contract(monkeypatch, tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    monkeypatch.setattr(api_deps, "get_settings", lambda: settings)
    monkeypatch.setattr(api_deps, "get_twin_service", lambda: FakeTwinService())
    client = TestClient(api_main.app)

    health = client.get("/api/ops/health")

    assert health.status_code == 200
    assert health.json()["services"][0]["name"] == "API"
    assert any(service["name"] == "Projector" for service in health.json()["services"])


def test_removed_productized_endpoints_return_404() -> None:
    client = TestClient(api_main.app)
    removed_routes = [
        "/api/forecast?pollutant=pm10",
        "/api/decision-support?pollutant=pm10",
        "/api/scenarios/catalog",
        "/api/scenarios/runs",
        "/api/twin/assets",
        "/api/twin/state?pollutant=pm10",
        "/api/twin/validation?pollutant=pm10",
    ]

    for route in removed_routes:
        response = client.get(route)
        assert response.status_code == 404
