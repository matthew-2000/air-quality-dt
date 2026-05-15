from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest

import api.autostart as autostart
from unisa_air_twin.config import load_settings


def test_optional_positive_int_env_defaults_and_zero(monkeypatch) -> None:
    monkeypatch.delenv("UNISA_AQDT_AUTO_INGEST_MAX_MESSAGES", raising=False)
    assert autostart._optional_positive_int_env("UNISA_AQDT_AUTO_INGEST_MAX_MESSAGES", 25) == 25

    monkeypatch.setenv("UNISA_AQDT_AUTO_INGEST_MAX_MESSAGES", "0")
    assert autostart._optional_positive_int_env("UNISA_AQDT_AUTO_INGEST_MAX_MESSAGES", 25) is None


def test_auto_ingest_loop_uses_bounded_max_messages(monkeypatch) -> None:
    settings = load_settings()
    for key in [
        "UNISA_MQTT_HOST",
        "UNISA_MQTT_PORT",
        "UNISA_MQTT_TOPIC",
        "UNISA_MQTT_USERNAME",
        "UNISA_MQTT_PASSWORD",
    ]:
        monkeypatch.setenv(key, "configured")

    monkeypatch.setenv("UNISA_AQDT_AUTO_INGEST", "true")
    monkeypatch.setenv("UNISA_AQDT_AUTO_INGEST_DURATION", "30")
    monkeypatch.setenv("UNISA_AQDT_AUTO_INGEST_INTERVAL", "10")
    monkeypatch.delenv("UNISA_AQDT_AUTO_INGEST_MAX_MESSAGES", raising=False)

    captured: dict[str, int | None] = {}
    refresh_calls: list[str] = []
    notified: list[str] = []

    monkeypatch.setattr(
        autostart,
        "collect_live_and_refresh",
        lambda _settings, duration_seconds, max_messages: captured.update(
            duration=duration_seconds,
            max_messages=max_messages,
        )
        or {"mqtt_messages": 25, "snapshot_rows": 12},
    )
    monkeypatch.setattr(
        autostart.job_registry,
        "create",
        lambda *args, **kwargs: SimpleNamespace(job_id="auto-job"),
    )
    monkeypatch.setattr(
        autostart.job_registry,
        "run",
        lambda _job_id, task, _settings: SimpleNamespace(status="completed", error=None, result=task()),
    )

    async def fake_sleep(_seconds: int) -> None:
        raise asyncio.CancelledError

    monkeypatch.setattr(autostart.anyio, "sleep", fake_sleep)

    class FakeService:
        def refresh(self) -> None:
            refresh_calls.append("refresh")

    class FakeEvents:
        async def notify(self) -> None:
            notified.append("notify")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(autostart.auto_ingest_loop(settings, FakeService, FakeEvents()))

    assert captured == {"duration": 30, "max_messages": 25}
    assert refresh_calls == ["refresh"]
    assert notified == ["notify"]
