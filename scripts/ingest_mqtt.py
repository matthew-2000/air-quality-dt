from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.config import load_settings
from unisa_air_twin.live_sensors import build_realtime_dataset, collect_mqtt_messages


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect live UNISA MQTT messages and rebuild app data.")
    parser.add_argument("--duration", type=int, default=60, help="Seconds to listen to the MQTT broker.")
    parser.add_argument("--max-messages", type=int, default=None, help="Optional message limit before disconnecting.")
    parser.add_argument("--no-build", action="store_true", help="Only append raw MQTT messages, without rebuilding parquet files.")
    parser.add_argument("--watch", action="store_true", help="Keep collecting in cycles and rebuilding datasets.")
    parser.add_argument("--interval", type=int, default=5, help="Pause in seconds between watch cycles.")
    args = parser.parse_args()

    settings = load_settings()
    while True:
        count = collect_mqtt_messages(settings, duration_seconds=args.duration, max_messages=args.max_messages)
        print(f"Collected {count:,} MQTT messages.")
        if not args.no_build:
            observations = build_realtime_dataset(settings)
            print(f"Rebuilt {len(observations):,} real sensor observation rows.")
        if not args.watch:
            break
        import time

        time.sleep(max(args.interval, 1))


if __name__ == "__main__":
    main()
