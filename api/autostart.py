from __future__ import annotations

import logging
import os
from collections.abc import Callable

import anyio

from api.events import SnapshotEventBus
from unisa_air_twin.config import Settings
from unisa_air_twin.product_jobs import collect_live_and_refresh, job_registry
from unisa_air_twin.ui_data import TwinDataService

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


def _mqtt_configured(settings: Settings) -> bool:
    broker = settings.live_sensors.get("broker", {})
    keys = [
        broker.get("host_env", "UNISA_MQTT_HOST"),
        broker.get("port_env", "UNISA_MQTT_PORT"),
        broker.get("topic_env", "UNISA_MQTT_TOPIC"),
        broker.get("username_env", "UNISA_MQTT_USERNAME"),
        broker.get("password_env", "UNISA_MQTT_PASSWORD"),
    ]
    return all(os.environ.get(key) for key in keys)


async def auto_ingest_loop(
    settings: Settings,
    service_factory: Callable[[], TwinDataService],
    events: SnapshotEventBus,
) -> None:
    if not _bool_env("UNISA_AQDT_AUTO_INGEST", True):
        return

    duration = _int_env("UNISA_AQDT_AUTO_INGEST_DURATION", 30)
    interval = _int_env("UNISA_AQDT_AUTO_INGEST_INTERVAL", 10)
    if not _mqtt_configured(settings):
        return

    while True:
        try:
            job = job_registry.create("auto_ingest_mqtt", "Ascolto MQTT automatico e refresh snapshot.")
            result = await anyio.to_thread.run_sync(
                job_registry.run,
                job.job_id,
                lambda: collect_live_and_refresh(settings, duration_seconds=max(duration, 1)),
            )
            if result.status == "completed":
                service_factory().refresh()
                await events.notify()
        except Exception:
            logger.exception("Automatic MQTT ingest loop failed")
        await anyio.sleep(max(interval, 1))
