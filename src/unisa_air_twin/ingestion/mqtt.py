from __future__ import annotations

import csv
import json
import os
import time
from typing import Any

import pandas as pd

from unisa_air_twin.config import Settings
from unisa_air_twin.event_log import publish_operational_event
from unisa_air_twin.external_sources import load_external_context
from unisa_air_twin.ingestion.normalization import _normalize_payload_record, _sensor_lookup
from unisa_air_twin.ingestion.runtime import configured_path
from unisa_air_twin.operational_store import append_raw_messages
from unisa_air_twin.projections import _frame_event_records
from unisa_air_twin.utils import ensure_dir, utc_now_iso


def collect_mqtt_messages(settings: Settings, duration_seconds: int = 60, max_messages: int | None = None) -> int:
    try:
        import paho.mqtt.client as mqtt
    except ImportError as exc:
        raise RuntimeError("Install paho-mqtt to collect live MQTT messages.") from exc

    broker = settings.live_sensors.get("broker", {})
    host = os.environ.get(broker.get("host_env", "UNISA_MQTT_HOST"))
    port_value = os.environ.get(broker.get("port_env", "UNISA_MQTT_PORT"))
    topic = os.environ.get(broker.get("topic_env", "UNISA_MQTT_TOPIC"))
    username = os.environ.get(broker.get("username_env", "UNISA_MQTT_USERNAME"))
    password = os.environ.get(broker.get("password_env", "UNISA_MQTT_PASSWORD"))
    if not host or not port_value or not topic or not username or not password:
        raise RuntimeError(
            "Missing MQTT connection settings. Set UNISA_MQTT_HOST, UNISA_MQTT_PORT, "
            "UNISA_MQTT_TOPIC, UNISA_MQTT_USERNAME, and UNISA_MQTT_PASSWORD."
        )
    port = int(port_value)

    jsonl_path = configured_path(settings, "mqtt_jsonl_path")
    csv_path = configured_path(settings, "mqtt_csv_path")
    ensure_dir(jsonl_path.parent)
    ensure_dir(csv_path.parent)

    metadata = _sensor_lookup(settings)
    external_context = load_external_context(settings)
    count = 0

    def on_connect(client: mqtt.Client, userdata: Any, flags: dict[str, Any], reason_code: int, properties: Any = None) -> None:
        client.subscribe(topic)

    def on_message(client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        nonlocal count
        received_at = pd.Timestamp.utcnow().tz_convert(settings.project.get("timezone", "Europe/Rome")).tz_localize(None)
        payload_text = message.payload.decode("utf-8", errors="replace")
        row = {
            "timestamp": received_at.isoformat(),
            "topic": message.topic,
            "payload": payload_text,
        }
        with jsonl_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        write_header = not csv_path.exists() or csv_path.stat().st_size == 0
        with csv_path.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=["timestamp", "topic", "payload"])
            if write_header:
                writer.writeheader()
            writer.writerow(row)
        append_raw_messages(settings, [{"received_at": row["timestamp"], "topic": row["topic"], "payload": row["payload"]}])
        try:
            payload = json.loads(payload_text)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            normalized_rows = _normalize_payload_record(
                settings,
                payload,
                message.topic,
                row["timestamp"],
                metadata,
                utc_now_iso(),
                external_context,
            )
            if normalized_rows:
                publish_operational_event(
                    settings,
                    "observations.upserted",
                    {
                        "rows": len(normalized_rows),
                        "topic": message.topic,
                        "received_at": row["timestamp"],
                        "sensor_id": str(payload.get("ID") or message.topic or ""),
                        "observations": _frame_event_records(pd.DataFrame(normalized_rows)),
                    },
                    aggregate_type="sensor",
                    aggregate_id=str(payload.get("ID") or message.topic or ""),
                    occurred_at=row["timestamp"],
                )
        count += 1
        if max_messages is not None and count >= max_messages:
            client.disconnect()

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    client.username_pw_set(username, password)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect(host, port, keepalive=30)
    client.loop_start()
    deadline = time.time() + max(1, duration_seconds)
    try:
        while time.time() < deadline and (max_messages is None or count < max_messages):
            time.sleep(0.2)
    finally:
        client.loop_stop()
        client.disconnect()
    return count
