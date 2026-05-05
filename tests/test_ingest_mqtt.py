from __future__ import annotations

import urllib.error

import scripts.ingest_mqtt as ingest_mqtt


def test_notify_snapshot_update_posts_to_api(monkeypatch) -> None:
    calls: list[tuple[str, bytes | None, str]] = []

    class FakeResponse:
        def __enter__(self) -> FakeResponse:
            return self

        def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
            return None

        def read(self) -> bytes:
            return b'{"status":"notified"}'

    def fake_urlopen(request: object, timeout: int) -> FakeResponse:
        calls.append((request.full_url, request.data, request.get_method()))
        assert timeout == 2
        return FakeResponse()

    monkeypatch.setattr(ingest_mqtt.urllib.request, "urlopen", fake_urlopen)

    ingest_mqtt.notify_snapshot_update("http://127.0.0.1:8000/api/events/snapshot")

    assert calls == [("http://127.0.0.1:8000/api/events/snapshot", b"", "POST")]


def test_notify_snapshot_update_ignores_unavailable_api(monkeypatch, capsys) -> None:
    def fake_urlopen(_request: object, timeout: int) -> object:
        assert timeout == 2
        raise urllib.error.URLError("api down")

    monkeypatch.setattr(ingest_mqtt.urllib.request, "urlopen", fake_urlopen)

    ingest_mqtt.notify_snapshot_update("http://127.0.0.1:8000/api/events/snapshot")

    assert "Snapshot update notification failed" in capsys.readouterr().err
