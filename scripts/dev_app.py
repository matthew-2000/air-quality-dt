from __future__ import annotations

import argparse
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def spawn_process(command: list[str], cwd: Path) -> subprocess.Popen[bytes]:
    return subprocess.Popen(command, cwd=cwd)


def terminate_process(process: subprocess.Popen[bytes]) -> None:
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the UNISA API and web cockpit together.")
    parser.add_argument("--with-ingest", action="store_true", help="Start continuous MQTT ingestion too.")
    parser.add_argument("--with-projector", action="store_true", help="Start projection worker too.")
    parser.add_argument("--mqtt-duration", type=int, default=30, help="Seconds for each ingest watch cycle.")
    parser.add_argument("--mqtt-interval", type=int, default=5, help="Pause in seconds between ingest cycles.")
    parser.add_argument("--api-port", type=int, default=8000, help="Port for the FastAPI server.")
    parser.add_argument("--web-port", type=int, default=5173, help="Port for the Vite dev server.")
    args = parser.parse_args()

    processes: list[subprocess.Popen[bytes]] = []

    api_command = [
        sys.executable,
        "-m",
        "uvicorn",
        "api.main:app",
        "--reload",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.api_port),
    ]
    web_command = [
        "npm",
        "--prefix",
        "web",
        "run",
        "dev",
        "--",
        "--host",
        "127.0.0.1",
        "--port",
        str(args.web_port),
    ]

    print(f"Starting API on http://127.0.0.1:{args.api_port}")
    processes.append(spawn_process(api_command, REPO_ROOT))
    print(f"Starting web app on http://127.0.0.1:{args.web_port}")
    processes.append(spawn_process(web_command, REPO_ROOT))

    if args.with_ingest:
        ingest_command = [
            sys.executable,
            "scripts/ingest_mqtt.py",
            "--watch",
            "--duration",
            str(args.mqtt_duration),
            "--interval",
            str(args.mqtt_interval),
        ]
        print("Starting continuous MQTT ingestion")
        processes.append(spawn_process(ingest_command, REPO_ROOT))

    if args.with_projector:
        projector_command = [sys.executable, "scripts/run_projector.py"]
        print("Starting projection worker")
        processes.append(spawn_process(projector_command, REPO_ROOT))

    def shutdown(_signum: int, _frame: object) -> None:
        for process in reversed(processes):
            terminate_process(process)
        raise SystemExit(0)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        while True:
            for process in processes:
                if process.poll() is not None:
                    raise SystemExit(process.returncode or 0)
            time.sleep(1)
    finally:
        for process in reversed(processes):
            terminate_process(process)


if __name__ == "__main__":
    main()
