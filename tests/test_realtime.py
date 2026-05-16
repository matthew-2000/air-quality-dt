from __future__ import annotations

from unisa_air_twin.config import load_settings
from unisa_air_twin.realtime import redis_channel, redis_enabled, redis_url


def test_realtime_defaults_without_redis(monkeypatch) -> None:
    settings = load_settings()
    monkeypatch.delenv("UNISA_AQDT_REDIS_URL", raising=False)

    assert redis_url(settings) is None
    assert redis_enabled(settings) is False
    assert redis_channel(settings) == "aqdt:snapshots"


def test_realtime_reads_env_overrides(monkeypatch) -> None:
    settings = load_settings()
    monkeypatch.setenv("UNISA_AQDT_REDIS_URL", "redis://redis:6379/0")
    monkeypatch.setenv("UNISA_AQDT_REDIS_CHANNEL", "aqdt:test")

    assert redis_url(settings) == "redis://redis:6379/0"
    assert redis_enabled(settings) is True
    assert redis_channel(settings) == "aqdt:test"
