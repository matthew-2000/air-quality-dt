from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
from typing import Any

from unisa_air_twin.config import Settings

logger = logging.getLogger(__name__)


def _realtime_config(settings: Settings) -> dict[str, Any]:
    return settings.live_sensors.get("realtime", {})


def redis_url(settings: Settings) -> str | None:
    config = _realtime_config(settings)
    value = str(
        config.get("redis_url")
        or os.environ.get(config.get("redis_url_env", "UNISA_AQDT_REDIS_URL"), "")
    ).strip()
    return value or None


def redis_channel(settings: Settings) -> str:
    config = _realtime_config(settings)
    return str(
        config.get("redis_channel")
        or os.environ.get(config.get("redis_channel_env", "UNISA_AQDT_REDIS_CHANNEL"), "aqdt:snapshots")
    ).strip()


def redis_enabled(settings: Settings) -> bool:
    return redis_url(settings) is not None


def publish_realtime_notification(settings: Settings, event_type: str, payload: dict[str, Any]) -> None:
    url = redis_url(settings)
    if not url:
        return
    try:
        import redis
    except ImportError:
        logger.warning("Redis realtime notification requested but `redis` package is unavailable.")
        return

    message = json.dumps({"event_type": event_type, "payload": payload}, ensure_ascii=False)
    try:
        client = redis.Redis.from_url(url, decode_responses=True)
        client.publish(redis_channel(settings), message)
        with contextlib.suppress(Exception):
            client.close()
    except Exception:
        logger.exception("Failed to publish realtime notification to Redis")


async def subscribe_realtime_notifications(settings: Settings, on_message: Any) -> None:
    url = redis_url(settings)
    if not url:
        while True:
            await asyncio.sleep(3600)
    try:
        import redis.asyncio as redis_async
    except ImportError:
        logger.warning("Redis realtime subscription requested but `redis` package is unavailable.")
        while True:
            await asyncio.sleep(3600)

    client = redis_async.from_url(url, decode_responses=True)
    pubsub = client.pubsub()
    try:
        await pubsub.subscribe(redis_channel(settings))
        while True:
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if not message:
                await asyncio.sleep(0.1)
                continue
            data = message.get("data")
            if not isinstance(data, str):
                continue
            try:
                decoded = json.loads(data)
            except json.JSONDecodeError:
                decoded = {"event_type": "unknown", "payload": {"raw": data}}
            await on_message(decoded)
    finally:
        with contextlib.suppress(Exception):
            await pubsub.unsubscribe(redis_channel(settings))
        with contextlib.suppress(Exception):
            await pubsub.close()
        with contextlib.suppress(Exception):
            await client.aclose()
