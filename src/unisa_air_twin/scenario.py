from __future__ import annotations

import pandas as pd

from unisa_air_twin.config import Settings


def apply_scenario(
    estimates: pd.DataFrame,
    settings: Settings,
    traffic_reduction: float = 0.0,
    wind_multiplier: float = 1.0,
    rain_event: bool = False,
    focus_zone: str = "all",
    green_improvement: float = 0.0,
) -> pd.DataFrame:
    if estimates.empty:
        return estimates.copy()
    df = estimates.copy()
    traffic_reduction = min(max(float(traffic_reduction), 0.0), 0.5)
    wind_multiplier = min(max(float(wind_multiplier), 0.5), 2.0)
    green_improvement = min(max(float(green_improvement), 0.0), 0.5)
    coefficients = settings.model["coefficients"]

    def scenario_value(row: pd.Series) -> float:
        pollutant = row["pollutant"]
        traffic_coeff = float(coefficients["traffic"].get(pollutant, 0.0))
        green_coeff = float(coefficients["green"].get(pollutant, 0.0))
        wind_coeff = float(coefficients["wind"].get(pollutant, 0.0))
        rain_coeff = float(coefficients["rain"].get(pollutant, 0.0))
        zone_multiplier = 1.0 if focus_zone == "all" or row.get("zone") == focus_zone else 0.25
        traffic_delta = -traffic_coeff * float(row.get("traffic_index", 0.0)) * traffic_reduction * zone_multiplier
        green_delta = -green_coeff * green_improvement * zone_multiplier
        baseline_wind = min(max(float(row.get("wind_speed_10m", 0.0)), 0.0), 10.0)
        scenario_wind = min(baseline_wind * wind_multiplier, 10.0)
        wind_delta = wind_coeff * (scenario_wind - baseline_wind) / 10.0
        rain_delta = rain_coeff if rain_event and float(row.get("precipitation", 0.0)) <= 0 else 0.0
        return max(0.0, float(row["estimated_value"]) + traffic_delta + green_delta + wind_delta + rain_delta)

    df["scenario_value"] = df.apply(scenario_value, axis=1).round(3)
    df["delta"] = (df["scenario_value"] - df["estimated_value"]).round(3)
    df["scenario_traffic_reduction"] = traffic_reduction
    df["scenario_wind_multiplier"] = wind_multiplier
    df["scenario_rain_event"] = rain_event
    df["scenario_focus_zone"] = focus_zone
    df["scenario_green_improvement"] = green_improvement
    return df


def latest_scenario_by_sensor(estimates: pd.DataFrame, settings: Settings, pollutant: str, **kwargs) -> pd.DataFrame:
    filtered = estimates[estimates["pollutant"] == pollutant].copy()
    if filtered.empty:
        return filtered
    latest_timestamp = filtered["timestamp"].max()
    latest = filtered[filtered["timestamp"] == latest_timestamp]
    return apply_scenario(latest, settings, **kwargs)


def scenario_summary(scenario_values: pd.DataFrame) -> dict:
    if scenario_values.empty or "delta" not in scenario_values.columns:
        return {
            "mean_delta": 0.0,
            "min_delta": 0.0,
            "max_delta": 0.0,
            "improved_sensors": 0,
            "rows": 0,
        }
    return {
        "mean_delta": round(float(scenario_values["delta"].mean()), 3),
        "min_delta": round(float(scenario_values["delta"].min()), 3),
        "max_delta": round(float(scenario_values["delta"].max()), 3),
        "improved_sensors": int((scenario_values["delta"] < 0).sum()),
        "rows": int(len(scenario_values)),
    }
