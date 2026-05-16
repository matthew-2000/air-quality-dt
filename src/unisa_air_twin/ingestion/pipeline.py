from __future__ import annotations

from unisa_air_twin.config import Settings
from unisa_air_twin.event_contract import OBSERVATIONS_REPLACED
from unisa_air_twin.event_log import publish_operational_event
from unisa_air_twin.ingestion.normalization import normalize_mqtt_observations
from unisa_air_twin.operational_store import read_snapshots
from unisa_air_twin.projections import (
    _frame_event_records,
    materialize_snapshot_projection,
    project_pending_events,
)


def build_realtime_dataset(settings: Settings):
    observations = normalize_mqtt_observations(settings)
    publish_operational_event(
        settings,
        OBSERVATIONS_REPLACED,
        {
            "rows": int(len(observations)),
            "observations": _frame_event_records(observations),
        },
        producer="ingestion.pipeline",
        aggregate_type="observation_projection",
        aggregate_id="full-rebuild",
    )
    project_pending_events(settings)
    return read_snapshots(settings)


def export_operational_artifacts(settings: Settings):
    return materialize_snapshot_projection(settings)
