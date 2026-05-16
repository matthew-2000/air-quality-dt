from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from unisa_air_twin.utils import utc_now_iso

EVENT_SCHEMA_VERSION = 1

OBSERVATIONS_TOPIC = "aqdt.observations"
SNAPSHOTS_TOPIC = "aqdt.snapshots"
DLQ_TOPIC = "aqdt.dlq"

OBSERVATIONS_UPSERTED = "observations.upserted"
OBSERVATIONS_REPLACED = "observations.replaced"
SNAPSHOTS_MATERIALIZED = "snapshots.materialized"
PROJECTION_DEAD_LETTERED = "projection.dead_lettered"

EVENT_TOPICS = {
    OBSERVATIONS_UPSERTED: OBSERVATIONS_TOPIC,
    OBSERVATIONS_REPLACED: OBSERVATIONS_TOPIC,
    SNAPSHOTS_MATERIALIZED: SNAPSHOTS_TOPIC,
    PROJECTION_DEAD_LETTERED: DLQ_TOPIC,
}


def event_topic(event_name: str) -> str:
    return EVENT_TOPICS.get(event_name, "aqdt.misc")


@dataclass(frozen=True)
class OperationalEventEnvelope:
    event_name: str
    topic: str
    schema_version: int
    producer: str
    occurred_at: str
    aggregate_type: str | None
    aggregate_id: str | None
    partition_key: str | None
    payload: dict[str, Any]
    event_id: int | None = None

    def to_record(self) -> dict[str, Any]:
        return {
            "event_name": self.event_name,
            "topic": self.topic,
            "schema_version": self.schema_version,
            "producer": self.producer,
            "occurred_at": self.occurred_at,
            "aggregate_type": self.aggregate_type,
            "aggregate_id": self.aggregate_id,
            "partition_key": self.partition_key,
            "payload": self.payload,
        }

    def to_broker_message(self) -> dict[str, Any]:
        message = self.to_record()
        if self.event_id is not None:
            message["event_id"] = self.event_id
        return message


def build_operational_event(
    event_name: str,
    payload: dict[str, Any],
    *,
    producer: str,
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    occurred_at: str | None = None,
    schema_version: int = EVENT_SCHEMA_VERSION,
) -> OperationalEventEnvelope:
    resolved_occurred_at = occurred_at or utc_now_iso()
    resolved_aggregate_id = aggregate_id or None
    return OperationalEventEnvelope(
        event_name=event_name,
        topic=event_topic(event_name),
        schema_version=schema_version,
        producer=producer,
        occurred_at=resolved_occurred_at,
        aggregate_type=aggregate_type,
        aggregate_id=resolved_aggregate_id,
        partition_key=resolved_aggregate_id,
        payload=payload,
    )


def parse_operational_event(record: dict[str, Any]) -> OperationalEventEnvelope:
    payload = record.get("payload") if isinstance(record.get("payload"), dict) else {}
    if {"event_name", "topic", "schema_version", "producer", "payload"} <= payload.keys():
        return OperationalEventEnvelope(
            event_name=str(payload.get("event_name") or record.get("event_type") or "unknown"),
            topic=str(payload.get("topic") or event_topic(str(record.get("event_type") or "unknown"))),
            schema_version=int(payload.get("schema_version") or 0),
            producer=str(payload.get("producer") or "unknown"),
            occurred_at=str(payload.get("occurred_at") or record.get("occurred_at") or ""),
            aggregate_type=str(payload.get("aggregate_type") or record.get("aggregate_type") or "") or None,
            aggregate_id=str(payload.get("aggregate_id") or record.get("aggregate_id") or "") or None,
            partition_key=str(payload.get("partition_key") or payload.get("aggregate_id") or record.get("aggregate_id") or "") or None,
            payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else {},
            event_id=int(record.get("event_id")) if record.get("event_id") is not None else None,
        )

    event_name = str(record.get("event_type") or payload.get("event_type") or "unknown")
    aggregate_id = str(record.get("aggregate_id") or payload.get("aggregate_id") or "") or None
    return OperationalEventEnvelope(
        event_name=event_name,
        topic=event_topic(event_name),
        schema_version=int(payload.get("schema_version") or 0),
        producer=str(payload.get("producer") or "legacy"),
        occurred_at=str(record.get("occurred_at") or payload.get("occurred_at") or ""),
        aggregate_type=str(record.get("aggregate_type") or payload.get("aggregate_type") or "") or None,
        aggregate_id=aggregate_id,
        partition_key=aggregate_id,
        payload=payload,
        event_id=int(record.get("event_id")) if record.get("event_id") is not None else None,
    )
