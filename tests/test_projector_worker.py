from __future__ import annotations

import pytest

from unisa_air_twin.config import load_settings
from unisa_air_twin.projector_worker import run_projection_cycle, run_projector_loop


def test_run_projection_cycle_uses_project_pending_events(monkeypatch) -> None:
    settings = load_settings()
    captured: dict[str, int] = {}

    monkeypatch.setattr(
        "unisa_air_twin.projector_worker.project_pending_events",
        lambda _settings, batch_size: captured.update(batch_size=batch_size) or {"snapshot_rows": 4},
    )

    result = run_projection_cycle(settings, batch_size=42)

    assert captured == {"batch_size": 42}
    assert result == {"snapshot_rows": 4}


def test_run_projector_loop_stops_when_disabled(monkeypatch) -> None:
    settings = load_settings()
    monkeypatch.setenv("UNISA_AQDT_AUTO_PROJECTOR", "false")

    called: list[str] = []
    monkeypatch.setattr("unisa_air_twin.projector_worker.project_pending_events", lambda *_args, **_kwargs: called.append("x"))

    run_projector_loop(settings)

    assert called == []


def test_run_projector_loop_runs_one_cycle(monkeypatch) -> None:
    settings = load_settings()
    monkeypatch.setenv("UNISA_AQDT_AUTO_PROJECTOR", "true")
    monkeypatch.setenv("UNISA_AQDT_PROJECTOR_INTERVAL", "1")

    called: list[str] = []

    monkeypatch.setattr(
        "unisa_air_twin.projector_worker.project_pending_events",
        lambda *_args, **_kwargs: called.append("cycle") or {"observation_changes": 1, "projected_events": 2, "snapshot_rows": 3},
    )
    monkeypatch.setattr(
        "unisa_air_twin.projector_worker.time.sleep",
        lambda _seconds: (_ for _ in ()).throw(KeyboardInterrupt),
    )

    with pytest.raises(KeyboardInterrupt):
        run_projector_loop(settings)

    assert called == ["cycle"]
