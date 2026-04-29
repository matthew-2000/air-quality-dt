from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.config import load_settings
from unisa_air_twin.live_sensors import build_realtime_dataset, write_real_sensor_geojson
from unisa_air_twin.osm import download_osm
from unisa_air_twin.zones import ensure_twin_layers


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the UNISA real-sensor pipeline.")
    parser.add_argument("--force", action="store_true", help="Redownload OSM layers even if cached.")
    args = parser.parse_args()

    settings = load_settings()
    print("1/3 Downloading OSM campus layers and preparing real sensors...")
    download_osm(settings, force=args.force)
    write_real_sensor_geojson(settings)
    ensure_twin_layers(settings)
    print("2/3 Building observations from UNISA MQTT exports...")
    observations = build_realtime_dataset(settings)
    print(f"   Real sensor rows available: {len(observations):,}")
    print("3/3 Pipeline complete. Run: streamlit run app/streamlit_app.py")


if __name__ == "__main__":
    main()
