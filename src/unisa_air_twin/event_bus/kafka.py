from __future__ import annotations

import json
import os
from typing import Any

from unisa_air_twin.config import Settings
from unisa_air_twin.event_contract import OperationalEventEnvelope


def _event_bus_config(settings: Settings) -> dict[str, Any]:
    return settings.live_sensors.get("event_bus", {})


def kafka_bootstrap_servers(settings: Settings) -> str:
    config = _event_bus_config(settings)
    return str(
        config.get("kafka_bootstrap_servers")
        or os.environ.get(config.get("kafka_bootstrap_servers_env", "UNISA_AQDT_KAFKA_BOOTSTRAP_SERVERS"), "")
    ).strip()


def kafka_consumer_group(settings: Settings) -> str:
    config = _event_bus_config(settings)
    return str(
        config.get("kafka_consumer_group")
        or os.environ.get(config.get("kafka_consumer_group_env", "UNISA_AQDT_KAFKA_CONSUMER_GROUP"), "aqdt-projector")
    ).strip()


def kafka_poll_timeout_ms(settings: Settings) -> int:
    config = _event_bus_config(settings)
    raw = str(
        config.get("kafka_poll_timeout_ms")
        or os.environ.get(config.get("kafka_poll_timeout_ms_env", "UNISA_AQDT_KAFKA_POLL_TIMEOUT_MS"), "1000")
    ).strip()
    try:
        return max(int(raw), 1)
    except ValueError:
        return 1000


def _load_kafka_classes() -> tuple[Any, Any]:
    try:
        from confluent_kafka import Consumer, Producer
    except ImportError as exc:  # pragma: no cover - optional runtime path
        raise RuntimeError(
            "Kafka event bus backend requires `confluent-kafka`. Install optional dependency and configure bootstrap servers."
        ) from exc
    return Consumer, Producer


class KafkaExternalBusPublisher:
    def publish(self, settings: Settings, envelope: OperationalEventEnvelope) -> None:
        bootstrap_servers = kafka_bootstrap_servers(settings)
        if not bootstrap_servers:
            raise RuntimeError("Kafka event bus backend selected but bootstrap servers missing.")
        _, producer_cls = _load_kafka_classes()
        producer = producer_cls({"bootstrap.servers": bootstrap_servers})
        producer.produce(envelope.topic, json.dumps(envelope.to_broker_message(), ensure_ascii=False).encode("utf-8"))
        producer.flush(kafka_poll_timeout_ms(settings))


class KafkaEventStreamConsumer:
    def fetch_events(
        self,
        settings: Settings,
        *,
        after_event_id: int,
        limit: int,
    ) -> list[dict]:
        bootstrap_servers = kafka_bootstrap_servers(settings)
        if not bootstrap_servers:
            raise RuntimeError("Kafka event bus backend selected but bootstrap servers missing.")
        consumer_cls, _ = _load_kafka_classes()
        consumer = consumer_cls(
            {
                "bootstrap.servers": bootstrap_servers,
                "group.id": kafka_consumer_group(settings),
                "enable.auto.commit": False,
                "auto.offset.reset": "earliest",
            }
        )
        topics = sorted(
            set(
                filter(
                    None,
                    [
                        os.environ.get("UNISA_AQDT_KAFKA_TOPIC_OBSERVATIONS", "aqdt.observations"),
                        os.environ.get("UNISA_AQDT_KAFKA_TOPIC_SNAPSHOTS", "aqdt.snapshots"),
                        os.environ.get("UNISA_AQDT_KAFKA_TOPIC_DLQ", "aqdt.dlq"),
                    ],
                )
            )
        )
        records: list[dict] = []
        try:
            consumer.subscribe(topics)
            while len(records) < limit:
                message = consumer.poll(kafka_poll_timeout_ms(settings) / 1000.0)
                if message is None:
                    break
                if message.error():
                    raise RuntimeError(str(message.error()))
                payload = json.loads(message.value().decode("utf-8"))
                event_id = int(payload.get("event_id") or 0)
                if event_id <= after_event_id:
                    continue
                records.append(
                    {
                        "event_id": event_id,
                        "event_type": str(payload.get("event_name") or "unknown"),
                        "aggregate_type": payload.get("aggregate_type"),
                        "aggregate_id": payload.get("aggregate_id"),
                        "occurred_at": payload.get("occurred_at"),
                        "payload": payload,
                    }
                )
        finally:  # pragma: no cover - optional runtime path
            consumer.close()
        return records
