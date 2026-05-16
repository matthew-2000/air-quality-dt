from __future__ import annotations

import asyncio

from api.events import SnapshotEventBus
from unisa_air_twin.config import load_settings
from unisa_air_twin.event_contract import (
    OBSERVATIONS_UPSERTED,
    SNAPSHOTS_MATERIALIZED,
    parse_operational_event,
)
from unisa_air_twin.operational_store import (
    append_operational_event,
    read_latest_event_id,
    read_operational_events,
)


def isolated_settings(tmp_path):
    settings = load_settings()
    settings.raw_dir = tmp_path / "raw"
    settings.processed_dir = tmp_path / "processed"
    settings.raw_dir.mkdir()
    settings.processed_dir.mkdir()
    settings.live_sensors["operational"] = {"db_path": str(settings.processed_dir / "realtime_operational.db")}
    return settings


def test_operational_event_log_persists_append_only_events(tmp_path) -> None:
    settings = isolated_settings(tmp_path)

    first_id = append_operational_event(
        settings,
        OBSERVATIONS_UPSERTED,
        {
            "event_name": OBSERVATIONS_UPSERTED,
            "topic": "aqdt.observations",
            "schema_version": 1,
            "producer": "test",
            "occurred_at": "2026-05-16T10:00:00",
            "aggregate_type": "sensor",
            "aggregate_id": "A",
            "partition_key": "A",
            "payload": {"rows": 2, "sensor_id": "A"},
        },
        aggregate_type="sensor",
        aggregate_id="A",
        occurred_at="2026-05-16T10:00:00",
    )
    second_id = append_operational_event(
        settings,
        SNAPSHOTS_MATERIALIZED,
        {
            "event_name": SNAPSHOTS_MATERIALIZED,
            "topic": "aqdt.snapshots",
            "schema_version": 1,
            "producer": "test",
            "occurred_at": "2026-05-16T10:01:00",
            "aggregate_type": "snapshot_projection",
            "aggregate_id": "2026-05-16T10:01:00",
            "partition_key": "2026-05-16T10:01:00",
            "payload": {"snapshot_rows": 4},
        },
        aggregate_type="snapshot_projection",
        aggregate_id="2026-05-16T10:01:00",
        occurred_at="2026-05-16T10:01:00",
    )

    assert second_id > first_id >= 1
    assert read_latest_event_id(settings) == second_id

    events = read_operational_events(settings, after_event_id=first_id - 1, limit=10)
    assert [event["event_type"] for event in events] == [
        OBSERVATIONS_UPSERTED,
        SNAPSHOTS_MATERIALIZED,
    ]
    envelope = parse_operational_event(events[0])
    assert envelope.topic == "aqdt.observations"
    assert envelope.payload["rows"] == 2


def test_snapshot_event_bus_observes_persisted_event_versions(tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    bus = SnapshotEventBus(lambda: settings)

    before = bus.version
    event_id = append_operational_event(
        settings,
        "snapshots.materialized",
        {"snapshot_rows": 1},
        occurred_at="2026-05-16T10:02:00",
    )

    async def wait_change() -> int:
        return await bus.wait_for_change(before, timeout=0.2)

    assert asyncio.run(wait_change()) == event_id
