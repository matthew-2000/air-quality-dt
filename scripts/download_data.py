from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.arpac import download_arpac
from unisa_air_twin.config import load_settings
from unisa_air_twin.osm import download_osm
from unisa_air_twin.sensors import create_virtual_sensors
from unisa_air_twin.weather import download_weather


def main() -> None:
    parser = argparse.ArgumentParser(description="Download public data for the UNISA Air Quality Digital Twin MVP.")
    parser.add_argument("--force", action="store_true", help="Redownload raw files even if cached.")
    parser.add_argument("--months", type=int, default=None, help="CSV resources per ARPAC dataset to download.")
    args = parser.parse_args()

    settings = load_settings()
    download_arpac(settings, force=args.force, months=args.months)
    download_weather(settings, force=args.force)
    download_osm(settings, force=args.force)
    create_virtual_sensors(settings)


if __name__ == "__main__":
    main()
