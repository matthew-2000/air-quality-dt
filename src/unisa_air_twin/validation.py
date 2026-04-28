from __future__ import annotations

import pandas as pd

from unisa_air_twin.arpac import POLLUTANT_VALID_RANGES
from unisa_air_twin.config import Settings
from unisa_air_twin.model import haversine_km, idw_interpolation
from unisa_air_twin.storage import read_table, write_table
from unisa_air_twin.utils import utc_now_iso, write_json


def _load_validation_frame(settings: Settings) -> pd.DataFrame:
    observations = read_table(settings.processed_dir / "air_quality_observations.parquet")
    stations = read_table(settings.processed_dir / "arpac_station_metadata.parquet")
    if observations.empty or stations.empty:
        return pd.DataFrame()
    observations = observations.copy()
    observations["timestamp"] = pd.to_datetime(observations["timestamp"], errors="coerce")
    merged = observations.merge(stations[["station_id", "lat", "lon"]], on="station_id", how="left")
    return merged.dropna(subset=["timestamp", "station_id", "lat", "lon"])


def leave_one_station_out_validation(settings: Settings, max_hours: int | None = None) -> pd.DataFrame:
    data = _load_validation_frame(settings)
    pollutants = [pollutant for pollutant in settings.model["pollutants"] if pollutant in data.columns]
    if data.empty or not pollutants:
        output = pd.DataFrame()
        write_table(output, settings.processed_dir / "model_validation.parquet")
        write_json(
            settings.processed_dir / "model_validation_summary.json",
            {
                "generated_at": utc_now_iso(),
                "rows": 0,
                "warning": "Dati ARPAC insufficienti per la validazione leave-one-station-out.",
            },
        )
        return output
    if max_hours is None:
        max_hours = int(getattr(settings, "validation", {}).get("max_hours", 168))
    data = data.sort_values("timestamp")
    if max_hours > 0:
        selected_timestamps = sorted(data["timestamp"].dropna().unique())[-max_hours:]
        data = data[data["timestamp"].isin(selected_timestamps)]

    rows: list[dict] = []
    idw_power = float(settings.model.get("idw_power", 2.0))
    for timestamp, hour_obs in data.groupby("timestamp"):
        for pollutant in pollutants:
            candidates = hour_obs.dropna(subset=[pollutant, "lat", "lon"]).copy()
            low, high = POLLUTANT_VALID_RANGES.get(pollutant, (0.0, 500.0))
            candidates = candidates[candidates[pollutant].between(low, high)]
            if candidates["station_id"].nunique() < 2:
                continue
            for _, held_out in candidates.iterrows():
                training = candidates[candidates["station_id"] != held_out["station_id"]]
                if training.empty:
                    continue
                distances = [
                    haversine_km(
                        float(held_out["lat"]),
                        float(held_out["lon"]),
                        float(row["lat"]),
                        float(row["lon"]),
                    )
                    for _, row in training.iterrows()
                ]
                predicted = idw_interpolation(training[pollutant].astype(float).tolist(), distances, power=idw_power)
                observed = float(held_out[pollutant])
                rows.append(
                    {
                        "timestamp": pd.Timestamp(timestamp),
                        "station_id": held_out["station_id"],
                        "station_name": held_out.get("station_name", held_out["station_id"]),
                        "pollutant": pollutant,
                        "observed": round(observed, 3),
                        "predicted": round(float(predicted), 3),
                        "error": round(float(predicted - observed), 3),
                        "absolute_error": round(abs(float(predicted - observed)), 3),
                        "training_station_count": int(training["station_id"].nunique()),
                        "nearest_training_station_km": round(float(min(distances)), 3),
                    }
                )

    validation = pd.DataFrame(rows)
    write_table(validation, settings.processed_dir / "model_validation.parquet")
    write_json(settings.processed_dir / "model_validation_summary.json", summarize_validation(validation))
    return validation


def summarize_validation(validation: pd.DataFrame) -> dict:
    if validation.empty:
        return {
            "generated_at": utc_now_iso(),
            "rows": 0,
            "pollutants": [],
            "overall": {"mae": None, "bias": None},
            "by_pollutant": [],
        }
    by_pollutant = (
        validation.groupby("pollutant", as_index=False)
        .agg(
            rows=("absolute_error", "count"),
            mae=("absolute_error", "mean"),
            bias=("error", "mean"),
            p90_absolute_error=("absolute_error", lambda values: values.quantile(0.9)),
        )
        .round(3)
        .sort_values("pollutant")
    )
    return {
        "generated_at": utc_now_iso(),
        "rows": int(len(validation)),
        "pollutants": sorted(validation["pollutant"].dropna().unique().tolist()),
        "overall": {
            "mae": round(float(validation["absolute_error"].mean()), 3),
            "bias": round(float(validation["error"].mean()), 3),
        },
        "by_pollutant": by_pollutant.to_dict(orient="records"),
    }
