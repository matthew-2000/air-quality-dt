from __future__ import annotations

import argparse
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from unisa_air_twin.config import load_settings
from unisa_air_twin.live_sensors import (
    build_realtime_dataset,
    collect_mqtt_messages,
    export_operational_artifacts,
)


def notify_snapshot_update(url: str | None) -> None:
    if not url:
        return
    request = urllib.request.Request(url, data=b"", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            response.read()
    except (TimeoutError, urllib.error.URLError) as exc:
        print(f"Snapshot update notification failed: {exc}", file=sys.stderr)


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect live UNISA MQTT messages and update operational app data.")
    parser.add_argument("--duration", type=int, default=60, help="Seconds to listen to the MQTT broker.")
    parser.add_argument("--max-messages", type=int, default=None, help="Optional message limit before disconnecting.")
    parser.add_argument("--no-build", action="store_true", help="Only append raw MQTT messages, without exporting app artifacts.")
    parser.add_argument("--watch", action="store_true", help="Keep collecting in cycles and exporting app artifacts.")
    parser.add_argument("--interval", type=int, default=5, help="Pause in seconds between watch cycles.")
    parser.add_argument(
        "--notify-url",
        default=os.environ.get("UNISA_AQDT_NOTIFY_URL"),
        help="Optional API URL to notify after operational artifacts are exported.",
    )
    args = parser.parse_args()

    settings = load_settings()
    while True:
        count = collect_mqtt_messages(settings, duration_seconds=args.duration, max_messages=args.max_messages)
        print(f"Collected {count:,} MQTT messages.")
        if not args.no_build:
            if args.watch:
                snapshots = export_operational_artifacts(settings)
                print(f"Exported {len(snapshots):,} snapshot rows from the operational store.")
            else:
                snapshots = build_realtime_dataset(settings)
                print(f"Rebuilt {len(snapshots):,} snapshot rows from raw MQTT history.")
            notify_snapshot_update(args.notify_url)
        if not args.watch:
            break
        import time

        time.sleep(max(args.interval, 1))


if __name__ == "__main__":
    main()
