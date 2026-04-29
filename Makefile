PYTHON ?= python3

.PHONY: install data app api web web-build test lint

install:
	$(PYTHON) -m pip install -e .

data:
	$(PYTHON) scripts/run_pipeline.py

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
