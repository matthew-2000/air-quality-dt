from __future__ import annotations

from unisa_air_twin.config import load_settings
from unisa_air_twin.zones import create_campus_zones, create_digital_twin_entities


def test_create_campus_zones_and_entities(tmp_path) -> None:
    settings = load_settings()
    settings.processed_dir = tmp_path
    zones = create_campus_zones(settings)
    entities = create_digital_twin_entities(settings)
    assert len(zones) >= 7
    assert (tmp_path / "campus_zones.geojson").exists()
    assert (tmp_path / "digital_twin_entities.json").exists()
    assert any(entity["type"] == "CampusZone" for entity in entities["entities"])
    assert any(entity["type"] == "VirtualSensor" for entity in entities["entities"])
