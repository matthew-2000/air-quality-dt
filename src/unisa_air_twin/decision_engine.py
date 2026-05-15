from __future__ import annotations

from typing import Any


def health_payload(summary: dict[str, Any], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    live_status = summary.get("live_feed", {}).get("status", "unknown")
    active_jobs = [job for job in jobs if job.get("status") in {"queued", "running"}]
    failed_jobs = [job for job in jobs if job.get("status") == "failed"]
    return {
        "services": [
            {"name": "API", "status": "ok", "detail": "FastAPI risponde"},
            {
                "name": "DB operativo",
                "status": "ok" if summary.get("observation_rows", 0) >= 0 else "warning",
                "detail": f"{summary.get('observation_rows', 0)} osservazioni",
            },
            {
                "name": "MQTT",
                "status": live_status,
                "detail": summary.get("live_feed", {}).get("latest_received_at"),
            },
            {
                "name": "Jobs",
                "status": "running" if active_jobs else "failed" if failed_jobs else "ok",
                "detail": f"{len(active_jobs)} attivi, {len(failed_jobs)} falliti",
            },
            {"name": "Stream SSE", "status": "ok", "detail": "endpoint /api/stream disponibile"},
            {"name": "Export", "status": "ok", "detail": "CSV/JSON via dashboard"},
        ],
        "backup": {
            "status": "manual",
            "restore_test": "not_configured",
            "last_backup": summary.get("ingestion", {}).get("generated_at"),
        },
    }
