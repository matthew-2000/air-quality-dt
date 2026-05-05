from __future__ import annotations

import asyncio
import json

from fastapi.testclient import TestClient

import api.main as api_main


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


def test_summary_contract_exposes_raw_and_observation_counts(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "get_twin_service", lambda: FakeTwinService())
    client = TestClient(api_main.app)

    response = client.get("/api/summary")

    assert response.status_code == 200
    payload = response.json()
    assert payload["raw_message_rows"] == 0
    assert payload["observation_rows"] == 0
    assert payload["sensor_health"][0]["status"] == "silent"


def test_timestamps_contract(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "get_twin_service", lambda: FakeTwinService())
    client = TestClient(api_main.app)

    response = client.get("/api/timestamps?pollutant=pm10")

    assert response.status_code == 200
    assert response.json() == {"timestamps": []}


def test_analytics_contract(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "get_twin_service", lambda: FakeTwinService())
    client = TestClient(api_main.app)

    response = client.get("/api/analytics?pollutant=pm10")

    assert response.status_code == 200
    assert response.json()["quality"]["rows"] == 0


def test_snapshot_event_notification_contract(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "get_twin_service", lambda: FakeTwinService())
    client = TestClient(api_main.app)

    before = api_main.snapshot_events.version
    response = client.post("/api/events/snapshot")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "notified"
    assert payload["version"] == before + 1


def test_stream_emits_connected_event(monkeypatch) -> None:
    monkeypatch.setattr(api_main, "get_twin_service", lambda: FakeTwinService())

    class FakeRequest:
        async def is_disconnected(self) -> bool:
            return False

    async def collect_first_event() -> str:
        stream = api_main._summary_stream(FakeRequest())
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
