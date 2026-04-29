from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.config import load_settings
from unisa_air_twin.live_sensors import write_real_sensor_geojson
from unisa_air_twin.osm import download_osm
from unisa_air_twin.zones import ensure_twin_layers


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare GIS layers and real UNISA sensor metadata.")
    parser.add_argument("--force", action="store_true", help="Redownload OSM layers even if cached.")
    args = parser.parse_args()

    settings = load_settings()
    download_osm(settings, force=args.force)
    write_real_sensor_geojson(settings)
    ensure_twin_layers(settings)


if __name__ == "__main__":
    main()
