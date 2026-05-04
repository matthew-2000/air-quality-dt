from __future__ import annotations

from typing import Any

import pandas as pd

VALUE_RULES = {
    "pm1": {"min": 0.0, "max": 150.0, "watch": 15.0},
    "pm25": {"min": 0.0, "max": 250.0, "watch": 15.0},
    "pm10": {"min": 0.0, "max": 500.0, "watch": 45.0},
    "voc_index": {"min": 0.0, "max": 500.0, "watch": 250.0},
    "nox_index": {"min": 0.0, "max": 500.0, "watch": 100.0},
}


def _quality_flags(row: pd.Series) -> list[str]:
    flags: list[str] = []
    pollutant = str(row.get("pollutant") or "")
    rules = VALUE_RULES.get(pollutant)
    value = pd.to_numeric(row.get("estimated_value"), errors="coerce")
    if pd.isna(value):
        flags.append("missing_value")
    elif rules:
        if float(value) < rules["min"] or float(value) > rules["max"]:
            flags.append("outside_operational_range")
        elif float(value) >= rules["watch"]:
            flags.append("elevated_value")

    timestamp = pd.to_datetime(row.get("timestamp"), errors="coerce")
    received_at = pd.to_datetime(row.get("received_at"), errors="coerce")
    if pd.isna(timestamp) or pd.isna(received_at):
        flags.append("missing_timestamp")
    else:
        latency_seconds = (pd.Timestamp(received_at) - pd.Timestamp(timestamp)).total_seconds()
        if latency_seconds < -30:
            flags.append("received_before_measured")
        elif latency_seconds > 300:
            flags.append("late_arrival")

    if pd.isna(pd.to_numeric(row.get("temperature"), errors="coerce")):
        flags.append("missing_temperature")
    if pd.isna(pd.to_numeric(row.get("humidity"), errors="coerce")):
        flags.append("missing_humidity")
    return flags


def _quality_label(flags: list[str]) -> str:
    critical = {"missing_value", "outside_operational_range", "missing_timestamp", "received_before_measured"}
    if critical.intersection(flags):
        return "critical"
    if flags:
        return "watch"
    return "ok"


def _quality_score(flags: list[str]) -> float:
    score = 1.0
    penalties = {
        "missing_value": 1.0,
        "outside_operational_range": 0.8,
        "missing_timestamp": 0.7,
        "received_before_measured": 0.5,
        "late_arrival": 0.25,
        "elevated_value": 0.15,
        "missing_temperature": 0.1,
        "missing_humidity": 0.1,
    }
    for flag in flags:
        score -= penalties.get(flag, 0.05)
    return round(max(score, 0.0), 3)


def annotate_quality(frame: pd.DataFrame) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()
    output = frame.copy()
    flags = output.apply(_quality_flags, axis=1)
    output["quality_flags"] = flags
    output["quality_label"] = flags.map(_quality_label)
    output["quality_score"] = flags.map(_quality_score)
    return output


def quality_summary(frame: pd.DataFrame) -> dict[str, Any]:
    if frame.empty:
        return {
            "rows": 0,
            "ok_rows": 0,
            "watch_rows": 0,
            "critical_rows": 0,
            "ok_ratio": 0.0,
            "flags": [],
        }
    annotated = frame if "quality_flags" in frame.columns else annotate_quality(frame)
    labels = annotated["quality_label"] if "quality_label" in annotated.columns else pd.Series(dtype=str)
    all_flags: dict[str, int] = {}
    for value in annotated["quality_flags"]:
        for flag in value if isinstance(value, list) else []:
            all_flags[flag] = all_flags.get(flag, 0) + 1
    rows = int(len(annotated))
    ok_rows = int(labels.eq("ok").sum())
    return {
        "rows": rows,
        "ok_rows": ok_rows,
        "watch_rows": int(labels.eq("watch").sum()),
        "critical_rows": int(labels.eq("critical").sum()),
        "ok_ratio": round(ok_rows / rows, 3) if rows else 0.0,
        "flags": [{"flag": flag, "rows": count} for flag, count in sorted(all_flags.items())],
    }
