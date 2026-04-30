VENV ?= .venv
SYSTEM_PYTHON ?= python3
PYTHON ?= $(VENV)/bin/python
MQTT_DURATION ?= 60
MQTT_INTERVAL ?= 5

.PHONY: venv install install-web bootstrap data data-live ingest-live app api web web-build test lint

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

app:
	$(PYTHON) -m streamlit run app/streamlit_app.py

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
