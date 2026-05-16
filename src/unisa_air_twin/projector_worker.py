from __future__ import annotations

import logging
import os
import time
from typing import Any

from unisa_air_twin.config import Settings
from unisa_air_twin.projections import project_pending_events

logger = logging.getLogger(__name__)


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


def _int_env(name: str, default: int) -> int:
    value = os.environ.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def run_projection_cycle(settings: Settings, batch_size: int | None = None) -> dict[str, Any]:
    effective_batch_size = batch_size or _int_env("UNISA_AQDT_PROJECTOR_BATCH_SIZE", 500)
    return project_pending_events(settings, batch_size=max(effective_batch_size, 1))


def run_projector_loop(settings: Settings) -> None:
    if not _bool_env("UNISA_AQDT_AUTO_PROJECTOR", True):
        return
    interval = max(_int_env("UNISA_AQDT_PROJECTOR_INTERVAL", 2), 1)
    while True:
        try:
            result = run_projection_cycle(settings)
            if result.get("observation_changes"):
                logger.info("Projected %s events into %s snapshot rows", result.get("projected_events"), result.get("snapshot_rows"))
            if result.get("retrying_events") or result.get("dlq_events"):
                logger.warning(
                    "Projection worker issues: retrying=%s dlq=%s blocked_event_id=%s",
                    result.get("retrying_events"),
                    result.get("dlq_events"),
                    result.get("blocked_event_id"),
                )
        except Exception:
            logger.exception("Projection worker cycle failed")
        time.sleep(interval)
