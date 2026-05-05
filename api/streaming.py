from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any, Protocol

from fastapi import Request

from api.events import SnapshotEventBus

STREAM_HEARTBEAT_SECONDS = 30.0
STREAM_RETRY_MILLISECONDS = 5000


class TwinServiceProtocol(Protocol):
    def summary(self) -> dict[str, Any]: ...


def summary_stream_fingerprint(summary: dict[str, Any]) -> str:
    coverage_rows = [
        {
            "pollutant": row.get("pollutant"),
            "active_sensors": row.get("active_sensors"),
            "capable_sensors": row.get("capable_sensors"),
            "coverage_ratio": row.get("coverage_ratio"),
        }
        for row in summary.get("coverage_by_pollutant", [])
        if isinstance(row, dict)
    ]
    fingerprint_payload = {
        "latest_timestamp": summary.get("latest_timestamp"),
        "latest_received_at": summary.get("latest_received_at"),
        "rows": summary.get("rows"),
        "snapshot_rows": summary.get("snapshot_rows"),
        "observation_rows": summary.get("observation_rows"),
        "raw_message_rows": summary.get("raw_message_rows"),
        "active_sensors": summary.get("active_sensors"),
        "capable_sensors": summary.get("capable_sensors"),
        "coverage_by_pollutant": coverage_rows,
        "generated_at": summary.get("ingestion", {}).get("generated_at") if isinstance(summary.get("ingestion"), dict) else None,
        "live_feed_status": summary.get("live_feed", {}).get("status") if isinstance(summary.get("live_feed"), dict) else None,
    }
    return json.dumps(fingerprint_payload, sort_keys=True, separators=(",", ":"))


def summary_stream_payload(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "fingerprint": summary_stream_fingerprint(summary),
        "latest_timestamp": summary.get("latest_timestamp"),
        "latest_received_at": summary.get("latest_received_at"),
        "snapshot_rows": int(summary.get("snapshot_rows", 0) or 0),
        "observation_rows": int(summary.get("observation_rows", 0) or 0),
        "raw_message_rows": int(summary.get("raw_message_rows", 0) or 0),
        "active_sensors": int(summary.get("active_sensors", 0) or 0),
        "live_feed_status": summary.get("live_feed", {}).get("status") if isinstance(summary.get("live_feed"), dict) else None,
        "generated_at": summary.get("ingestion", {}).get("generated_at") if isinstance(summary.get("ingestion"), dict) else None,
    }


def sse_event(name: str, payload: dict[str, Any], retry: int | None = None) -> str:
    lines: list[str] = []
    if retry is not None:
        lines.append(f"retry: {retry}")
    lines.append(f"event: {name}")
    body = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    for line in body.splitlines() or [body]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


async def summary_stream(
    request: Request,
    events: SnapshotEventBus,
    service_factory: Callable[[], TwinServiceProtocol],
) -> AsyncIterator[str]:
    last_fingerprint: str | None = None
    observed_version = events.version
    service = service_factory()
    while True:
        if await request.is_disconnected():
            break
        try:
            payload = summary_stream_payload(service.summary())
            if payload["fingerprint"] != last_fingerprint:
                event_name = "connected" if last_fingerprint is None else "snapshot_update"
                retry = STREAM_RETRY_MILLISECONDS if last_fingerprint is None else None
                yield sse_event(event_name, payload, retry=retry)
                last_fingerprint = str(payload["fingerprint"])
        except Exception as exc:
            yield sse_event("stream_error", {"message": str(exc)})
        current_version = events.version
        observed_version = current_version
        next_version = await events.wait_for_change(observed_version, STREAM_HEARTBEAT_SECONDS)
        if next_version == observed_version:
            yield ": heartbeat\n\n"
        observed_version = next_version
