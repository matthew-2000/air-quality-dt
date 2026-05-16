from __future__ import annotations

import logging
import os

from unisa_air_twin.config import Settings
from unisa_air_twin.event_bus.base import EventStreamConsumer, ExternalBusPublisher
from unisa_air_twin.event_bus.kafka import KafkaEventStreamConsumer, KafkaExternalBusPublisher
from unisa_air_twin.event_bus.store import NoopExternalBusPublisher, StoreEventStreamConsumer
from unisa_air_twin.event_contract import OperationalEventEnvelope

logger = logging.getLogger(__name__)


def event_bus_backend(settings: Settings) -> str:
    config = settings.live_sensors.get("event_bus", {})
    value = str(
        config.get("backend")
        or os.environ.get(config.get("backend_env", "UNISA_AQDT_EVENT_BUS_BACKEND"), "store")
    ).strip()
    return value or "store"


def get_event_stream_consumer(settings: Settings) -> EventStreamConsumer:
    backend = event_bus_backend(settings)
    if backend == "store":
        return StoreEventStreamConsumer()
    if backend == "kafka":
        return KafkaEventStreamConsumer()
    raise RuntimeError(f"Unsupported event bus backend: {backend}")


def get_external_bus_publisher(settings: Settings) -> ExternalBusPublisher:
    backend = event_bus_backend(settings)
    if backend == "store":
        return NoopExternalBusPublisher()
    if backend == "kafka":
        return KafkaExternalBusPublisher()
    raise RuntimeError(f"Unsupported event bus backend: {backend}")


def fan_out_operational_event(settings: Settings, envelope: OperationalEventEnvelope) -> None:
    publisher = get_external_bus_publisher(settings)
    try:
        publisher.publish(settings, envelope)
    except RuntimeError:
        raise
    except Exception:  # pragma: no cover - defensive runtime path
        logger.exception("Failed to fan out operational event to external bus")
