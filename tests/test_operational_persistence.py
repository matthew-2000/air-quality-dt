from __future__ import annotations

from unisa_air_twin.config import load_settings
from unisa_air_twin.decision_engine import ScenarioRun, ScenarioRunStore
from unisa_air_twin.operational_store import read_job_run, read_scenario_runs
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
