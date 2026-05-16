from __future__ import annotations

import logging
from dataclasses import replace
from typing import Any

from unisa_air_twin.config import Settings
from unisa_air_twin.event_bus import fan_out_operational_event
from unisa_air_twin.event_contract import OperationalEventEnvelope, build_operational_event
from unisa_air_twin.operational_store import append_operational_event

logger = logging.getLogger(__name__)


def publish_operational_event(
    settings: Settings,
    event: str | OperationalEventEnvelope,
    payload: dict[str, Any] | None = None,
    *,
    producer: str = "unisa_air_twin",
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    occurred_at: str | None = None,
) -> int:
    envelope = (
        event
        if isinstance(event, OperationalEventEnvelope)
        else build_operational_event(
            event,
            payload or {},
            producer=producer,
            aggregate_type=aggregate_type,
            aggregate_id=aggregate_id,
            occurred_at=occurred_at,
        )
    )
    event_id = append_operational_event(
        settings,
        envelope.event_name,
        envelope.to_record(),
        aggregate_type=envelope.aggregate_type,
        aggregate_id=envelope.aggregate_id,
        occurred_at=envelope.occurred_at,
    )
    stored_envelope = replace(envelope, event_id=event_id)
    try:
        fan_out_operational_event(settings, stored_envelope)
    except RuntimeError:
        logger.exception("External event bus fan-out failed for event_id=%s", event_id)
    return event_id
