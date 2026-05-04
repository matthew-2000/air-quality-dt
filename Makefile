VENV ?= .venv
SYSTEM_PYTHON ?= python3
PYTHON ?= $(VENV)/bin/python
MQTT_DURATION ?= 60
MQTT_INTERVAL ?= 5

.PHONY: venv install install-web bootstrap data data-live ingest-live dev dev-live api web web-build test lint clean clean-ui clean-data-live clean-data-legacy

venv:
	@if [ ! -x "$(PYTHON)" ]; then $(SYSTEM_PYTHON) -m venv $(VENV); fi
	$(PYTHON) -m pip install --upgrade pip

install: venv
	$(PYTHON) -m pip install -e .

install-web:
	npm --prefix web install

bootstrap: install install-web

data:
	$(PYTHON) scripts/run_pipeline.py

data-live:
	$(PYTHON) scripts/download_data.py
	$(PYTHON) scripts/ingest_mqtt.py --duration $(MQTT_DURATION)

ingest-live:
	$(PYTHON) scripts/ingest_mqtt.py --watch --duration $(MQTT_DURATION) --interval $(MQTT_INTERVAL)

dev:
	$(PYTHON) scripts/dev_app.py

dev-live:
	$(PYTHON) scripts/dev_app.py --with-ingest --mqtt-duration $(MQTT_DURATION) --mqtt-interval $(MQTT_INTERVAL)

api:
	$(PYTHON) -m uvicorn api.main:app --reload

web:
	npm --prefix web run dev

web-build:
	npm --prefix web run build

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

clean:
	rm -rf api/__pycache__ scripts/__pycache__ src/unisa_air_twin/__pycache__ tests/__pycache__ .pytest_cache .ruff_cache web/dist

clean-ui:
	rm -f web/tmp-ui-*.png

clean-data-live:
	rm -f data/raw/live_sensors/mqtt_data.csv data/raw/live_sensors/mqtt_raw.jsonl
	rm -f data/processed/realtime_operational.db
	rm -f data/processed/real_sensor_observations.parquet
	rm -f data/processed/campus_air_quality_estimates.parquet
	rm -f data/processed/realtime_ingestion_summary.json

clean-data-legacy:
	rm -f data/raw/sensesquare/mqtt_data.csv data/raw/sensesquare/mqtt_raw.jsonl data/raw/sensesquare/sensor_PEDT.json
	rm -f data/processed/air_quality_observations.parquet
	rm -f data/processed/arpac_station_metadata.parquet
	rm -f data/processed/campus_virtual_sensors.geojson
	rm -f data/processed/model_validation.parquet
	rm -f data/processed/model_validation_summary.json
	rm -f data/processed/unisa_weather_inspection.json
	rm -f data/processed/weather_hourly.parquet
