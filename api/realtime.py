from __future__ import annotations

import logging

from api.events import SnapshotEventBus
from unisa_air_twin.config import Settings
from unisa_air_twin.realtime import redis_enabled, subscribe_realtime_notifications

logger = logging.getLogger(__name__)


async def realtime_notification_loop(settings: Settings, events: SnapshotEventBus) -> None:
    if not redis_enabled(settings):
        return

    async def on_message(_message: dict) -> None:
        await events.notify()

    try:
        await subscribe_realtime_notifications(settings, on_message)
    except Exception:
        logger.exception("Realtime notification loop failed")
