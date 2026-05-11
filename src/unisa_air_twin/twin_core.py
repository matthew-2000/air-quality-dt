from __future__ import annotations

from typing import Any

import pandas as pd

from unisa_air_twin.decision_engine import forecast_payload, risk_level


def _feature_name(feature: dict[str, Any], fallback: str) -> str:
    properties = feature.get("properties") or {}
    return str(properties.get("name") or properties.get("zone_name") or properties.get("zone") or fallback)


def _feature_asset_id(layer_name: str, index: int, feature: dict[str, Any]) -> str:
    properties = feature.get("properties") or {}
    raw_id = properties.get("id") or properties.get("osm_id") or properties.get("zone")
    return f"{layer_name}:{raw_id or index}"


def _numeric_series(frame: pd.DataFrame, column: str) -> pd.Series:
    if frame.empty or column not in frame.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(frame[column], errors="coerce")


def asset_registry_payload(summary: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
    sensors = data.get("sensors", pd.DataFrame())
    layers = data.get("layers", {})
    assets: list[dict[str, Any]] = [
        {
            "asset_id": "campus:unisa-fisciano",
            "kind": "campus",
            "name": summary.get("campus", {}).get("name", "Campus di Fisciano"),
            "status": "active",
            "lat": summary.get("campus", {}).get("latitude"),
            "lon": summary.get("campus", {}).get("longitude"),
            "properties": {"source": summary.get("source"), "mode": summary.get("mode")},
        }
    ]
    relationships: list[dict[str, str]] = []

    if isinstance(sensors, pd.DataFrame) and not sensors.empty:
        health_by_sensor = {row.get("sensor_id"): row for row in summary.get("sensor_health", [])}
        for row in sensors.to_dict(orient="records"):
            sensor_id = str(row.get("sensor_id"))
            health = health_by_sensor.get(sensor_id, {})
            zone = row.get("zone")
            assets.append(
                {
                    "asset_id": f"sensor:{sensor_id}",
                    "kind": "sensor",
                    "name": row.get("name") or sensor_id,
                    "status": health.get("status", "unknown"),
                    "lat": row.get("lat"),
                    "lon": row.get("lon"),
                    "properties": {
                        "zone": zone,
                        "pollutants": health.get("pollutants", []),
                        "coordinate_quality": row.get("coordinate_quality"),
                        "latest_received_at": health.get("latest_received_at"),
                        "latest_measured_at": health.get("latest_measured_at"),
                    },
                }
            )
            relationships.append({"source": f"sensor:{sensor_id}", "target": "campus:unisa-fisciano", "type": "located_in"})
            if zone:
                relationships.append({"source": f"sensor:{sensor_id}", "target": f"zones:{zone}", "type": "observes"})

    for layer_name, collection in layers.items():
        features = (collection or {}).get("features", []) if isinstance(collection, dict) else []
        for index, feature in enumerate(features):
            asset_id = _feature_asset_id(layer_name, index, feature)
            assets.append(
                {
                    "asset_id": asset_id,
                    "kind": layer_name.rstrip("s") if layer_name.endswith("s") else layer_name,
                    "name": _feature_name(feature, asset_id),
                    "status": "mapped",
                    "lat": None,
                    "lon": None,
                    "properties": dict(feature.get("properties") or {}),
                }
            )
            relationships.append({"source": asset_id, "target": "campus:unisa-fisciano", "type": "part_of"})

    kind_counts: dict[str, int] = {}
    for asset in assets:
        kind = str(asset["kind"])
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    return {
        "assets": assets,
        "relationships": relationships,
        "counts": kind_counts,
    }


def state_payload(
    summary: dict[str, Any],
    snapshot: pd.DataFrame,
    analytics: dict[str, Any],
    pollutant: str,
    timestamp: str | None,
) -> dict[str, Any]:
    active = int(summary.get("active_sensors") or 0)
    if not active and "sensor_id" in snapshot.columns:
        active = int(snapshot["sensor_id"].nunique())
    capable = int(summary.get("capable_sensors") or active)
    coverage = float(summary.get("coverage_ratio") or 0.0)
    if not coverage and capable:
        coverage = round(float(active) / capable, 3)
    feed_status = (summary.get("live_feed") or {}).get("status", "unknown")
    status = "no_data" if snapshot.empty else "operational"
    if status == "operational" and (coverage < 0.7 or feed_status in {"stale", "unconfigured"}):
        status = "degraded"

    ages = _numeric_series(snapshot, "reading_age_seconds")
    values = _numeric_series(snapshot, "estimated_value")
    uncertainty = _numeric_series(snapshot, "uncertainty_score")
    state_quality = {
        "coverage_ratio": coverage,
        "active_sensors": active,
        "capable_sensors": capable,
        "median_age_seconds": int(ages.median()) if not ages.dropna().empty else None,
        "mean_uncertainty": round(float(uncertainty.mean()), 3) if not uncertainty.dropna().empty else None,
        "value_min": round(float(values.min()), 3) if not values.dropna().empty else None,
        "value_max": round(float(values.max()), 3) if not values.dropna().empty else None,
        "feed_status": feed_status,
    }

    sensor_states: list[dict[str, Any]] = []
    if not snapshot.empty:
        for row in snapshot.to_dict(orient="records"):
            sensor_states.append(
                {
                    "asset_id": f"sensor:{row.get('sensor_id')}",
                    "sensor_id": row.get("sensor_id"),
                    "name": row.get("sensor_name"),
                    "status": row.get("quality_status") or row.get("confidence_label"),
                    "value": row.get("estimated_value"),
                    "reading_age_seconds": row.get("reading_age_seconds"),
                    "zone": row.get("zone"),
                }
            )

    zone_states = []
    for row in analytics.get("zone_summary", []):
        mean_value = row.get("mean_value")
        zone_states.append(
            {
                "asset_id": f"zones:{row.get('zone')}",
                "zone": row.get("zone"),
                "zone_name": row.get("zone_name") or row.get("zone"),
                "mean_value": mean_value,
                "risk": risk_level(mean_value, pollutant),
                "sensors": row.get("sensors"),
                "quality_ok_ratio": row.get("quality_ok_ratio"),
            }
        )

    gaps = []
    if feed_status in {"stale", "unconfigured"}:
        gaps.append({"type": "live_feed", "severity": "warning", "detail": f"feed {feed_status}"})
    if coverage < 0.7:
        gaps.append({"type": "coverage", "severity": "warning", "detail": f"coverage {coverage:.0%}"})
    if snapshot.empty:
        gaps.append({"type": "snapshot", "severity": "critical", "detail": "no canonical snapshot available"})

    return {
        "state_id": f"{pollutant}:{timestamp or 'latest'}",
        "pollutant": pollutant,
        "timestamp": timestamp,
        "status": status,
        "quality": state_quality,
        "entities": {"sensors": sensor_states, "zones": zone_states},
        "gaps": gaps,
    }


def validation_payload(
    observations: pd.DataFrame,
    snapshot: pd.DataFrame,
    pollutant: str,
    timestamp: str | None,
) -> dict[str, Any]:
    if not timestamp or observations.empty:
        return {
            "pollutant": pollutant,
            "timestamp": timestamp,
            "status": "insufficient_data",
            "metrics": {"mae": None, "bias": None, "validated_windows": 0},
            "windows": [],
        }

    baseline = pd.Timestamp(timestamp)
    frame = observations.copy()
    frame["timestamp"] = pd.to_datetime(frame.get("timestamp"), errors="coerce")
    frame = frame[frame["pollutant"] == pollutant].dropna(subset=["timestamp"])
    forecast = forecast_payload(frame, snapshot, pollutant, timestamp)
    windows = []
    errors = []
    for window in forecast.get("windows", []):
        minutes = int(window.get("minutes", 0))
        target = baseline + pd.Timedelta(minutes=minutes)
        tolerance = pd.Timedelta(minutes=10 if minutes <= 60 else 20)
        actual_frame = frame[(frame["timestamp"] >= target - tolerance) & (frame["timestamp"] <= target + tolerance)]
        actual_mean = (
            float(pd.to_numeric(actual_frame.get("estimated_value"), errors="coerce").mean())
            if not actual_frame.empty
            else None
        )
        expected = window.get("expected_value")
        error = round(float(actual_mean) - float(expected), 3) if actual_mean is not None and expected is not None else None
        if error is not None:
            errors.append(error)
        windows.append(
            {
                "minutes": minutes,
                "target_timestamp": target.strftime("%Y-%m-%dT%H:%M:%S"),
                "expected_value": expected,
                "actual_value": round(actual_mean, 3) if actual_mean is not None else None,
                "error": error,
                "status": "validated" if error is not None else "pending",
                "sample_rows": int(len(actual_frame)),
            }
        )

    absolute_errors = [abs(error) for error in errors]
    status = "validated" if errors else "pending"
    return {
        "pollutant": pollutant,
        "timestamp": timestamp,
        "status": status,
        "metrics": {
            "mae": round(float(sum(absolute_errors) / len(absolute_errors)), 3) if absolute_errors else None,
            "bias": round(float(sum(errors) / len(errors)), 3) if errors else None,
            "validated_windows": len(errors),
        },
        "windows": windows,
    }
