VENV ?= .venv
SYSTEM_PYTHON ?= python3
PYTHON ?= $(VENV)/bin/python
DEV_ARGS ?=

.PHONY: venv install install-web bootstrap dev api web build test lint clean

venv:
	@if [ ! -x "$(PYTHON)" ]; then $(SYSTEM_PYTHON) -m venv $(VENV); fi
	$(PYTHON) -m pip install --upgrade pip

install: venv
	$(PYTHON) -m pip install -e .

install-web:
	npm --prefix web install

bootstrap: install install-web

dev:
	$(PYTHON) scripts/dev_app.py $(DEV_ARGS)

api:
	$(PYTHON) -m uvicorn api.main:app --reload

web:
	npm --prefix web run dev

build:
	npm --prefix web run build

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .

clean:
	rm -rf api/__pycache__ app/__pycache__ scripts/__pycache__ src/unisa_air_twin/__pycache__ tests/__pycache__ .pytest_cache .ruff_cache cache web/dist
