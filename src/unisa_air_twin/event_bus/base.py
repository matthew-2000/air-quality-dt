from __future__ import annotations

from typing import Protocol

from unisa_air_twin.config import Settings
from unisa_air_twin.event_contract import OperationalEventEnvelope


class EventStreamConsumer(Protocol):
    def fetch_events(
        self,
        settings: Settings,
        *,
        after_event_id: int,
        limit: int,
    ) -> list[dict]: ...


class ExternalBusPublisher(Protocol):
    def publish(self, settings: Settings, envelope: OperationalEventEnvelope) -> None: ...
