from __future__ import annotations

from unisa_air_twin.config import Settings
from unisa_air_twin.operational_store import read_operational_events


class StoreEventStreamConsumer:
    def fetch_events(
        self,
        settings: Settings,
        *,
        after_event_id: int,
        limit: int,
    ) -> list[dict]:
        return read_operational_events(settings, after_event_id=after_event_id, limit=limit)


class NoopExternalBusPublisher:
    def publish(self, settings: Settings, envelope: object) -> None:  # pragma: no cover - trivial
        return None
