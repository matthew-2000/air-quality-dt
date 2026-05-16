from __future__ import annotations

from unisa_air_twin.config import load_settings
from unisa_air_twin.event_contract import OBSERVATIONS_UPSERTED
from unisa_air_twin.event_log import publish_operational_event
from unisa_air_twin.operational_store import (
    read_observations,
    read_projection_failure_summary,
    read_snapshots,
)
from unisa_air_twin.projections import project_pending_events, rebuild_projections_from_event_log


def isolated_settings(tmp_path):
    settings = load_settings()
    settings.raw_dir = tmp_path / "raw"
    settings.processed_dir = tmp_path / "processed"
    settings.raw_dir.mkdir()
    settings.processed_dir.mkdir()
    settings.live_sensors["operational"] = {"db_path": str(settings.processed_dir / "realtime_operational.db")}
    return settings


def observation(sensor_id: str, pollutant: str, value: float, ts: str) -> dict[str, object]:
    return {
        "timestamp": ts,
        "received_at": ts,
        "sensor_id": sensor_id,
        "sensor_name": f"Sensore {sensor_id}",
        "lat": 40.771,
        "lon": 14.79,
        "zone": "campus",
        "pollutant": pollutant,
        "base_value": value,
        "estimated_value": value,
        "is_real": True,
    }


def test_project_pending_events_materializes_read_models(tmp_path) -> None:
    settings = isolated_settings(tmp_path)

    publish_operational_event(
        settings,
        "observations.upserted",
        {
            "rows": 2,
            "observations": [
                observation("A", "pm10", 11.0, "2026-05-16T10:00:00"),
                observation("A", "pm25", 7.0, "2026-05-16T10:00:00"),
            ],
        },
        aggregate_type="sensor",
        aggregate_id="A",
    )

    result = project_pending_events(settings)

    observations = read_observations(settings)
    snapshots = read_snapshots(settings)
    assert result["observation_changes"] == 1
    assert set(observations["pollutant"]) == {"pm10", "pm25"}
    assert set(snapshots["pollutant"]) == {"pm10", "pm25"}


def test_rebuild_projections_replays_latest_replace_then_upserts(tmp_path) -> None:
    settings = isolated_settings(tmp_path)

    publish_operational_event(
        settings,
        "observations.replaced",
        {
            "rows": 1,
            "observations": [observation("A", "pm10", 10.0, "2026-05-16T10:00:00")],
        },
        aggregate_type="observation_projection",
        aggregate_id="full-rebuild",
    )
    publish_operational_event(
        settings,
        "observations.upserted",
        {
            "rows": 1,
            "observations": [observation("B", "pm25", 8.0, "2026-05-16T10:01:00")],
        },
        aggregate_type="sensor",
        aggregate_id="B",
    )

    result = rebuild_projections_from_event_log(settings)

    observations = read_observations(settings).sort_values(["sensor_id", "pollutant"]).reset_index(drop=True)
    assert result["observation_changes"] == 2
    assert observations["sensor_id"].tolist() == ["A", "B"]
    assert observations["estimated_value"].tolist() == [10.0, 8.0]
    assert not read_snapshots(settings).empty


def test_project_pending_events_stops_on_retryable_failure(tmp_path, monkeypatch) -> None:
    settings = isolated_settings(tmp_path)
    monkeypatch.setenv("UNISA_AQDT_PROJECTOR_MAX_RETRIES", "3")

    publish_operational_event(
        settings,
        OBSERVATIONS_UPSERTED,
        {"rows": 1, "observations": "broken"},
        producer="test",
        aggregate_type="sensor",
        aggregate_id="broken",
    )

    result = project_pending_events(settings)

    assert result["retrying_events"] == 1
    assert result["blocked_event_id"] >= 1
    assert read_observations(settings).empty
    assert read_projection_failure_summary(settings)["retrying"] == 1


def test_project_pending_events_dead_letters_poison_event_after_retry_limit(tmp_path, monkeypatch) -> None:
    settings = isolated_settings(tmp_path)
    monkeypatch.setenv("UNISA_AQDT_PROJECTOR_MAX_RETRIES", "2")

    publish_operational_event(
        settings,
        OBSERVATIONS_UPSERTED,
        {"rows": 1, "observations": "broken"},
        producer="test",
        aggregate_type="sensor",
        aggregate_id="broken",
    )
    publish_operational_event(
        settings,
        OBSERVATIONS_UPSERTED,
        {
            "rows": 1,
            "observations": [observation("B", "pm25", 8.0, "2026-05-16T10:01:00")],
        },
        producer="test",
        aggregate_type="sensor",
        aggregate_id="B",
    )

    first = project_pending_events(settings)
    second = project_pending_events(settings)

    observations = read_observations(settings)
    failures = read_projection_failure_summary(settings)
    assert first["retrying_events"] == 1
    assert second["dlq_events"] == 1
    assert set(observations["sensor_id"]) == {"B"}
    assert failures["retrying"] == 0
    assert failures["dead_lettered"] == 1
