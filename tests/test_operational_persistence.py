from __future__ import annotations

import pandas as pd

from unisa_air_twin.config import load_settings
from unisa_air_twin.decision_engine import ScenarioRun, ScenarioRunStore
from unisa_air_twin.operational_store import (
    read_job_run,
    read_scenario_runs,
    read_sensor_observations,
    read_sensor_snapshot,
    read_sensor_timeseries,
    read_snapshot,
    read_snapshot_timestamps,
    replace_observations,
    replace_snapshots,
)
from unisa_air_twin.product_jobs import JobRegistry


def isolated_settings(tmp_path):
    settings = load_settings()
    settings.raw_dir = tmp_path / "raw"
    settings.processed_dir = tmp_path / "processed"
    settings.raw_dir.mkdir()
    settings.processed_dir.mkdir()
    settings.live_sensors["operational"] = {"db_path": str(settings.processed_dir / "realtime_operational.db")}
    return settings


def test_job_registry_persists_status_transitions(tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    registry = JobRegistry()

    job = registry.create("refresh_snapshots", settings=settings)
    registry.run(job.job_id, lambda: {"snapshot_rows": 4}, settings=settings)

    persisted = read_job_run(settings, job.job_id)
    assert persisted is not None
    assert persisted["status"] == "completed"
    assert persisted["result"] == {"snapshot_rows": 4}

    reloaded = JobRegistry().get(job.job_id, settings=settings)
    assert reloaded is not None
    assert reloaded.status == "completed"


def test_scenario_store_persists_runs(tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    store = ScenarioRunStore()
    run = ScenarioRun(
        run_id="scenario-1",
        name="Riduzione traffico",
        scenario_type="traffic_reduction",
        pollutant="pm10",
        intensity=1.0,
        created_at="2026-05-11T10:00:00Z",
        baseline_timestamp="2026-05-11T09:55:00",
        parameters={"source": "test"},
        output={"delta_mean": -2.5},
    )

    store.add(run, settings=settings)

    persisted = read_scenario_runs(settings)
    assert persisted[0]["run_id"] == "scenario-1"
    assert persisted[0]["parameters"] == {"source": "test"}
    assert persisted[0]["output"] == {"delta_mean": -2.5}


def test_targeted_snapshot_queries_do_not_require_full_store_scan(tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    snapshots = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-05-11 10:00:00"),
                "received_at": pd.Timestamp("2026-05-11 10:00:10"),
                "sensor_id": "A",
                "sensor_name": "Sensore A",
                "pollutant": "pm10",
                "estimated_value": 12.0,
            },
            {
                "timestamp": pd.Timestamp("2026-05-11 10:01:00"),
                "received_at": pd.Timestamp("2026-05-11 10:01:10"),
                "sensor_id": "B",
                "sensor_name": "Sensore B",
                "pollutant": "pm25",
                "estimated_value": 7.0,
            },
        ]
    )
    replace_snapshots(settings, snapshots)

    assert read_snapshot_timestamps(settings, "pm10") == ["2026-05-11T10:00:00"]
    assert read_snapshot(settings, "pm10", "2026-05-11T10:00:00")["sensor_id"].tolist() == ["A"]
    assert read_sensor_snapshot(settings, "B", "2026-05-11T10:01:00")["pollutant"].tolist() == ["pm25"]


def test_targeted_sensor_history_queries(tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    observations = pd.DataFrame(
        [
            {
                "timestamp": pd.Timestamp("2026-05-11 10:00:00"),
                "received_at": pd.Timestamp("2026-05-11 10:00:10"),
                "sensor_id": "A",
                "sensor_name": "Sensore A",
                "pollutant": "pm10",
                "estimated_value": 12.0,
            },
            {
                "timestamp": pd.Timestamp("2026-05-11 10:01:00"),
                "received_at": pd.Timestamp("2026-05-11 10:01:10"),
                "sensor_id": "B",
                "sensor_name": "Sensore B",
                "pollutant": "pm25",
                "estimated_value": 7.0,
            },
        ]
    )
    replace_observations(settings, observations)

    assert read_sensor_observations(settings, "A")["sensor_name"].tolist() == ["Sensore A"]
    assert read_sensor_timeseries(settings, "pm25", "Sensore B")["estimated_value"].tolist() == [7.0]
