from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.config import load_settings
from unisa_air_twin.ingestion import collect_mqtt_messages
from unisa_air_twin.product_jobs import rebuild_operational_dataset, refresh_operational_snapshots


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect live UNISA MQTT messages and update operational app data.")
    parser.add_argument("--duration", type=int, default=60, help="Seconds to listen to the MQTT broker.")
    parser.add_argument("--max-messages", type=int, default=None, help="Optional message limit before disconnecting.")
    parser.add_argument("--no-build", action="store_true", help="Only append raw MQTT messages, without exporting app artifacts.")
    parser.add_argument("--watch", action="store_true", help="Keep collecting in cycles and exporting app artifacts.")
    parser.add_argument("--interval", type=int, default=5, help="Pause in seconds between watch cycles.")
    args = parser.parse_args()

    settings = load_settings()
    while True:
        count = collect_mqtt_messages(settings, duration_seconds=args.duration, max_messages=args.max_messages)
        print(f"Collected {count:,} MQTT messages.")
        if not args.no_build:
            if args.watch:
                result = refresh_operational_snapshots(settings)
                print(f"Exported {result['snapshot_rows']:,} snapshot rows from the operational store.")
            else:
                result = rebuild_operational_dataset(settings)
                print(f"Rebuilt {result['snapshot_rows']:,} snapshot rows from raw MQTT history.")
        if not args.watch:
            break
        import time

        time.sleep(max(args.interval, 1))


if __name__ == "__main__":
    main()
