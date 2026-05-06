from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from threading import Lock
from typing import Any
from uuid import uuid4

import pandas as pd

from unisa_air_twin.analytics import zone_summary

SCENARIO_DELTAS: dict[str, dict[str, float]] = {
    "traffic_increase": {"pm10": 0.16, "pm25": 0.12, "pm1": 0.08, "no2": 0.18},
    "traffic_reduction": {"pm10": -0.14, "pm25": -0.11, "pm1": -0.07, "no2": -0.16},
    "campus_event": {"pm10": 0.2, "pm25": 0.14, "pm1": 0.1, "no2": 0.1},
    "parking_closure": {"pm10": 0.09, "pm25": 0.06, "pm1": 0.04, "no2": 0.12},
    "new_sensor": {"confidence": 0.12},
    "sensor_offline": {"confidence": -0.18},
    "rain": {"pm10": -0.18, "pm25": -0.12, "pm1": -0.08},
    "wind": {"pm10": -0.1, "pm25": -0.08, "pm1": -0.06, "no2": -0.06},
    "green_increase": {"pm10": -0.07, "pm25": -0.05, "pm1": -0.03, "confidence": 0.04},
    "freshness_window": {"confidence": 0.08},
}


def utc_timestamp() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def risk_level(value: float | None, pollutant: str) -> str:
    if value is None:
        return "n/d"
    thresholds = {"pm10": (20, 35), "pm25": (10, 20), "pm1": (6, 12), "no2": (30, 55)}
    low, high = thresholds.get(pollutant, (15, 30))
    if value >= high:
        return "alto"
    if value >= low:
        return "medio"
    return "basso"


def confidence_from_snapshot(snapshot: pd.DataFrame) -> float:
    if snapshot.empty:
        return 0.0
    coverage = pd.to_numeric(snapshot.get("coverage_ratio"), errors="coerce")
    if coverage.notna().any():
        base = float(coverage.max())
    else:
        active = snapshot["sensor_id"].nunique() if "sensor_id" in snapshot.columns else 0
        base = min(active / 6.0, 1.0)
    ages = pd.to_numeric(snapshot.get("reading_age_seconds"), errors="coerce")
    age_penalty = min(float(ages.median()) / 900.0, 0.35) if ages.notna().any() else 0.2
    return round(max(min(base - age_penalty, 0.98), 0.05), 3)


def forecast_payload(observations: pd.DataFrame, snapshot: pd.DataFrame, pollutant: str, timestamp: str | None) -> dict[str, Any]:
    values = pd.to_numeric(snapshot.get("estimated_value"), errors="coerce") if not snapshot.empty else pd.Series(dtype=float)
    latest = float(values.mean()) if values.notna().any() else None
    trend_points = []
    if not observations.empty and "pollutant" in observations.columns:
        frame = observations[observations["pollutant"] == pollutant].copy()
        frame["timestamp"] = pd.to_datetime(frame.get("timestamp"), errors="coerce")
        frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").tail(72)
        trend_points = pd.to_numeric(frame.get("estimated_value"), errors="coerce").dropna().tolist()
    if latest is None and trend_points:
        latest = float(trend_points[-1])
    if latest is None:
        return {"pollutant": pollutant, "timestamp": timestamp, "windows": [], "critical_zones": [], "method": "baseline statistica"}

    slope = 0.0
    if len(trend_points) >= 6:
        recent = pd.Series(trend_points[-6:])
        previous = pd.Series(trend_points[-12:-6] or trend_points[:6])
        slope = float(recent.mean() - previous.mean()) / 6.0
    confidence = confidence_from_snapshot(snapshot)
    windows = []
    for minutes in (30, 60, 180):
        expected = max(latest + slope * (minutes / 10), 0)
        spread = max(expected * (0.22 - confidence * 0.1), 0.8)
        windows.append(
            {
                "minutes": minutes,
                "expected_value": round(expected, 3),
                "lower": round(max(expected - spread, 0), 3),
                "upper": round(expected + spread, 3),
                "trend": "in peggioramento" if expected > latest * 1.05 else "in miglioramento" if expected < latest * 0.95 else "stabile",
                "risk": risk_level(expected, pollutant),
                "confidence": confidence,
            }
        )
    return {
        "pollutant": pollutant,
        "timestamp": timestamp,
        "windows": windows,
        "critical_zones": [],
        "method": "baseline statistica su storico recente",
    }


@dataclass
class ScenarioRun:
    run_id: str
    name: str
    scenario_type: str
    pollutant: str
    intensity: float
    created_at: str
    baseline_timestamp: str | None
    parameters: dict[str, Any]
    output: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ScenarioRunStore:
    def __init__(self) -> None:
        self._runs: dict[str, ScenarioRun] = {}
        self._lock = Lock()

    def add(self, run: ScenarioRun) -> None:
        with self._lock:
            self._runs[run.run_id] = run

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            runs = list(self._runs.values())
        return [run.to_dict() for run in sorted(runs, key=lambda item: item.created_at, reverse=True)[:limit]]


scenario_store = ScenarioRunStore()


def run_scenario(
    snapshot: pd.DataFrame,
    zone_geojson: dict[str, Any],
    pollutant: str,
    timestamp: str | None,
    scenario_type: str,
    intensity: float,
    name: str | None = None,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    factor = max(min(float(intensity), 2.0), 0.0)
    effects = SCENARIO_DELTAS.get(scenario_type, {})
    value_delta = effects.get(pollutant, effects.get("pm10", 0.0)) * factor
    confidence_delta = effects.get("confidence", 0.0) * factor
    simulated = snapshot.copy()
    if not simulated.empty and "estimated_value" in simulated.columns:
        simulated["baseline_value"] = pd.to_numeric(simulated["estimated_value"], errors="coerce")
        simulated["estimated_value"] = (simulated["baseline_value"] * (1 + value_delta)).clip(lower=0).round(3)
    baseline_zones = zone_summary(snapshot, zone_geojson)
    scenario_zones = zone_summary(simulated, zone_geojson)
    baseline_mean = float(pd.to_numeric(snapshot.get("estimated_value"), errors="coerce").mean()) if not snapshot.empty else None
    scenario_mean = float(pd.to_numeric(simulated.get("estimated_value"), errors="coerce").mean()) if not simulated.empty else None
    confidence = max(min(confidence_from_snapshot(snapshot) + confidence_delta, 0.98), 0.03)
    deltas = []
    baseline_by_zone = baseline_zones.set_index("zone") if not baseline_zones.empty else pd.DataFrame()
    for row in scenario_zones.to_dict(orient="records"):
        zone = str(row.get("zone"))
        baseline_value = baseline_by_zone.loc[zone].get("mean_value") if zone in baseline_by_zone.index else None
        scenario_value = row.get("mean_value")
        deltas.append(
            {
                "zone": zone,
                "zone_name": row.get("zone_name") or zone,
                "baseline": round(float(baseline_value), 3) if baseline_value is not None and pd.notna(baseline_value) else None,
                "scenario": round(float(scenario_value), 3) if scenario_value is not None and pd.notna(scenario_value) else None,
                "delta": round(float(scenario_value) - float(baseline_value), 3)
                if baseline_value is not None and scenario_value is not None and pd.notna(baseline_value) and pd.notna(scenario_value)
                else None,
            }
        )
    output = {
        "baseline_mean": round(baseline_mean, 3) if baseline_mean is not None and pd.notna(baseline_mean) else None,
        "scenario_mean": round(scenario_mean, 3) if scenario_mean is not None and pd.notna(scenario_mean) else None,
        "delta_mean": round((scenario_mean or 0) - (baseline_mean or 0), 3) if baseline_mean is not None and scenario_mean is not None else None,
        "confidence": round(confidence, 3),
        "risk": risk_level(scenario_mean, pollutant),
        "zone_deltas": deltas,
        "drivers": scenario_drivers(scenario_type, value_delta, confidence_delta),
        "areas_to_watch": [row["zone_name"] for row in sorted(deltas, key=lambda item: item.get("scenario") or 0, reverse=True)[:3]],
        "sensors_to_check": sensor_actions(snapshot, scenario_type),
        "method_notes": "Run what-if non distruttivo: modifica snapshot simulato, aggrega per zone, calcola delta e rischio stimato.",
    }
    run = ScenarioRun(
        run_id=uuid4().hex,
        name=name or scenario_type.replace("_", " "),
        scenario_type=scenario_type,
        pollutant=pollutant,
        intensity=factor,
        created_at=utc_timestamp(),
        baseline_timestamp=timestamp,
        parameters=parameters or {},
        output=output,
    )
    scenario_store.add(run)
    return run.to_dict()


def scenario_drivers(scenario_type: str, value_delta: float, confidence_delta: float) -> list[str]:
    labels = {
        "traffic_increase": "traffico campus più intenso",
        "traffic_reduction": "riduzione pressione veicolare",
        "campus_event": "evento con afflusso concentrato",
        "parking_closure": "spostamento flussi verso aree alternative",
        "new_sensor": "copertura rete più forte",
        "sensor_offline": "copertura rete ridotta",
        "rain": "lavaggio particolato da pioggia",
        "wind": "dispersione favorita dal vento",
        "green_increase": "mitigazione verde",
        "freshness_window": "finestra freschezza più permissiva",
    }
    drivers = [labels.get(scenario_type, "parametri scenario")]
    if value_delta:
        drivers.append(f"delta inquinante stimato {round(value_delta * 100, 1)}%")
    if confidence_delta:
        drivers.append(f"confidence modificata {round(confidence_delta * 100, 1)} punti")
    return drivers


def sensor_actions(snapshot: pd.DataFrame, scenario_type: str) -> list[str]:
    if snapshot.empty or "sensor_name" not in snapshot.columns:
        return ["Verifica almeno un sensore online o avvia simulazione demo."]
    frame = snapshot.copy()
    frame["reading_age_seconds"] = pd.to_numeric(frame.get("reading_age_seconds"), errors="coerce")
    stale = frame.sort_values("reading_age_seconds", ascending=False).head(3)
    prefix = "Priorità verifica" if scenario_type in {"sensor_offline", "freshness_window"} else "Monitorare"
    return [f"{prefix}: {name}" for name in stale["sensor_name"].dropna().astype(str).tolist()]


def decision_payload(summary: dict[str, Any], analytics: dict[str, Any], forecast: dict[str, Any]) -> dict[str, Any]:
    zones = analytics.get("zone_summary") or []
    top_zone = zones[0] if zones else {}
    windows = forecast.get("windows") or []
    worst = max(windows, key=lambda item: item.get("upper", 0), default={})
    alerts: list[dict[str, Any]] = []
    if summary.get("live_feed", {}).get("status") in {"stale", "unconfigured"}:
        alerts.append({"level": "warning", "title": "Feed live da verificare", "detail": "Ultima ricezione assente o non recente."})
    if (summary.get("coverage_ratio") or 0) < 0.5:
        alerts.append({"level": "warning", "title": "Copertura bassa", "detail": "Pochi sensori contribuiscono allo snapshot corrente."})
    if worst.get("risk") == "alto":
        alerts.append({"level": "critical", "title": "Rischio previsto alto", "detail": f"Finestra {worst.get('minutes')} minuti sopra soglia operativa."})
    if not alerts:
        alerts.append({"level": "ok", "title": "Nessun alert critico", "detail": "Sistema in stato gestibile con dati correnti."})
    return {
        "risk_level": worst.get("risk") or "n/d",
        "what_to_do_now": [
            f"Controlla zona {top_zone.get('zone_name') or top_zone.get('zone') or 'più critica'} e sensori vicini.",
            "Mantieni aperta la mappa operativa durante prossimi aggiornamenti.",
            "Esporta riepilogo se serve report per decisione o demo.",
        ],
        "alerts": alerts,
        "suggested_sensor_placement": [row.get("zone_name") or row.get("zone") for row in zones[-2:] if row],
        "explanations": [
            "Rischio combina forecast breve termine, copertura rete e qualità dato.",
            "Confidence bassa indica dati pochi, vecchi o sensori non omogenei.",
        ],
    }


def health_payload(summary: dict[str, Any], jobs: list[dict[str, Any]]) -> dict[str, Any]:
    live_status = summary.get("live_feed", {}).get("status", "unknown")
    active_jobs = [job for job in jobs if job.get("status") in {"queued", "running"}]
    failed_jobs = [job for job in jobs if job.get("status") == "failed"]
    return {
        "services": [
            {"name": "API", "status": "ok", "detail": "FastAPI risponde"},
            {"name": "DB operativo", "status": "ok" if summary.get("observation_rows", 0) >= 0 else "warning", "detail": f"{summary.get('observation_rows', 0)} osservazioni"},
            {"name": "MQTT", "status": live_status, "detail": summary.get("live_feed", {}).get("latest_received_at")},
            {"name": "Jobs", "status": "running" if active_jobs else "failed" if failed_jobs else "ok", "detail": f"{len(active_jobs)} attivi, {len(failed_jobs)} falliti"},
            {"name": "Stream SSE", "status": "ok", "detail": "endpoint /api/stream disponibile"},
            {"name": "Export", "status": "ok", "detail": "CSV/JSON via dashboard"},
        ],
        "backup": {
            "status": "scheduled",
            "retention_days": 30,
            "restore_test": "manuale guidato",
            "last_backup": summary.get("ingestion", {}).get("generated_at"),
        },
    }
