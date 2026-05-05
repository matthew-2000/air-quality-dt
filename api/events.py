from __future__ import annotations

import asyncio


class SnapshotEventBus:
    def __init__(self) -> None:
        self._condition = asyncio.Condition()
        self._version = 0

    @property
    def version(self) -> int:
        return self._version

    async def notify(self) -> int:
        async with self._condition:
            self._version += 1
            self._condition.notify_all()
            return self._version

    async def wait_for_change(self, version: int, timeout: float) -> int:
        async with self._condition:
            if self._version != version:
                return self._version
            try:
                await asyncio.wait_for(self._condition.wait_for(lambda: self._version != version), timeout=timeout)
            except TimeoutError:
                return version
            return self._version


snapshot_events = SnapshotEventBus()
