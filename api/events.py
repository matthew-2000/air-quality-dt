from __future__ import annotations

import asyncio
from collections.abc import Callable

from unisa_air_twin.config import Settings, load_settings
from unisa_air_twin.operational_store import read_latest_event_id


class SnapshotEventBus:
    def __init__(self, settings_factory: Callable[[], Settings] | None = None) -> None:
        self._condition = asyncio.Condition()
        self._version = 0
        self._settings_factory = settings_factory

    def _persistent_version(self) -> int:
        if self._settings_factory is None:
            return 0
        try:
            return read_latest_event_id(self._settings_factory())
        except Exception:
            return 0

    @property
    def version(self) -> int:
        return max(self._version, self._persistent_version())

    async def notify(self) -> int:
        async with self._condition:
            self._version = self.version + 1
            self._condition.notify_all()
            return self.version

    async def wait_for_change(self, version: int, timeout: float) -> int:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            current = self.version
            if current != version:
                return current
            remaining = deadline - loop.time()
            if remaining <= 0:
                return version
            async with self._condition:
                try:
                    await asyncio.wait_for(self._condition.wait(), timeout=min(remaining, 1.0))
                except TimeoutError:
                    pass


snapshot_events = SnapshotEventBus(load_settings)
