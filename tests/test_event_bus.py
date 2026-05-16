from __future__ import annotations

from unisa_air_twin.config import load_settings
from unisa_air_twin.event_bus import event_bus_backend, get_event_stream_consumer
from unisa_air_twin.event_log import publish_operational_event


def isolated_settings(tmp_path):
    settings = load_settings()
    settings.raw_dir = tmp_path / "raw"
    settings.processed_dir = tmp_path / "processed"
    settings.raw_dir.mkdir()
    settings.processed_dir.mkdir()
    settings.live_sensors["operational"] = {"db_path": str(settings.processed_dir / "realtime_operational.db")}
    return settings


def test_event_bus_defaults_to_store(tmp_path, monkeypatch) -> None:
    settings = isolated_settings(tmp_path)
    monkeypatch.delenv("UNISA_AQDT_EVENT_BUS_BACKEND", raising=False)

    consumer = get_event_stream_consumer(settings)

    assert event_bus_backend(settings) == "store"
    assert consumer.__class__.__name__ == "StoreEventStreamConsumer"


def test_store_event_consumer_reads_store_events(tmp_path) -> None:
    settings = isolated_settings(tmp_path)
    consumer = get_event_stream_consumer(settings)
    event_id = publish_operational_event(
        settings,
        "observations.upserted",
        {"rows": 1, "observations": []},
        producer="test",
        aggregate_type="sensor",
        aggregate_id="A",
    )

    events = consumer.fetch_events(settings, after_event_id=0, limit=10)

    assert len(events) == 1
    assert events[0]["event_id"] == event_id
    assert events[0]["event_type"] == "observations.upserted"


def test_publish_operational_event_fans_out_stored_event_id(tmp_path, monkeypatch) -> None:
    settings = isolated_settings(tmp_path)
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "unisa_air_twin.event_log.fan_out_operational_event",
        lambda _settings, envelope: captured.update(event_id=envelope.event_id, topic=envelope.topic),
    )

    event_id = publish_operational_event(
        settings,
        "snapshots.materialized",
        {"snapshot_rows": 2},
        producer="test",
        aggregate_type="snapshot_projection",
        aggregate_id="ts-1",
    )

    assert captured == {"event_id": event_id, "topic": "aqdt.snapshots"}
