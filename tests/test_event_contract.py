from __future__ import annotations

from unisa_air_twin.event_contract import (
    EVENT_SCHEMA_VERSION,
    OBSERVATIONS_UPSERTED,
    SNAPSHOTS_MATERIALIZED,
    build_operational_event,
    parse_operational_event,
)


def test_build_operational_event_assigns_topic_and_partition_key() -> None:
    envelope = build_operational_event(
        OBSERVATIONS_UPSERTED,
        {"rows": 2},
        producer="ingestion.mqtt",
        aggregate_type="sensor",
        aggregate_id="sensor-A",
        occurred_at="2026-05-16T10:00:00",
    )

    assert envelope.topic == "aqdt.observations"
    assert envelope.schema_version == EVENT_SCHEMA_VERSION
    assert envelope.partition_key == "sensor-A"
    assert envelope.payload["rows"] == 2


def test_parse_operational_event_supports_enveloped_store_record() -> None:
    envelope = parse_operational_event(
        {
            "event_id": 7,
            "event_type": SNAPSHOTS_MATERIALIZED,
            "aggregate_type": "snapshot_projection",
            "aggregate_id": "2026-05-16T10:02:00",
            "occurred_at": "2026-05-16T10:02:00",
            "payload": {
                "event_name": SNAPSHOTS_MATERIALIZED,
                "topic": "aqdt.snapshots",
                "schema_version": 1,
                "producer": "projection.snapshot",
                "occurred_at": "2026-05-16T10:02:00",
                "aggregate_type": "snapshot_projection",
                "aggregate_id": "2026-05-16T10:02:00",
                "partition_key": "2026-05-16T10:02:00",
                "payload": {"snapshot_rows": 3},
            },
        }
    )

    assert envelope.event_id == 7
    assert envelope.event_name == SNAPSHOTS_MATERIALIZED
    assert envelope.topic == "aqdt.snapshots"
    assert envelope.payload["snapshot_rows"] == 3


def test_parse_operational_event_supports_legacy_payload_shape() -> None:
    envelope = parse_operational_event(
        {
            "event_id": 4,
            "event_type": OBSERVATIONS_UPSERTED,
            "aggregate_type": "sensor",
            "aggregate_id": "A",
            "occurred_at": "2026-05-16T10:00:00",
            "payload": {"rows": 1, "observations": [{"sensor_id": "A"}]},
        }
    )

    assert envelope.event_id == 4
    assert envelope.event_name == OBSERVATIONS_UPSERTED
    assert envelope.topic == "aqdt.observations"
    assert envelope.producer == "legacy"
    assert envelope.payload["rows"] == 1
