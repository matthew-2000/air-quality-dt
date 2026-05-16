from __future__ import annotations

import sys
from pathlib import Path

import scripts.ingest_mqtt as ingest_mqtt


def test_ingest_script_uses_ingestion_module_exports() -> None:
    assert ingest_mqtt.collect_mqtt_messages is not None
    assert str(Path(ingest_mqtt.__file__).resolve().parents[1] / "src") in sys.path
