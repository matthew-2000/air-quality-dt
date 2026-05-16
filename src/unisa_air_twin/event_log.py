from __future__ import annotations

from typing import Any

from unisa_air_twin.config import Settings
from unisa_air_twin.operational_store import append_operational_event
from unisa_air_twin.utils import utc_now_iso


def publish_operational_event(
    settings: Settings,
    event_type: str,
    payload: dict[str, Any],
    *,
    aggregate_type: str | None = None,
    aggregate_id: str | None = None,
    occurred_at: str | None = None,
) -> int:
    return append_operational_event(
        settings,
        event_type,
        payload,
        aggregate_type=aggregate_type,
        aggregate_id=aggregate_id,
        occurred_at=occurred_at or utc_now_iso(),
    )
