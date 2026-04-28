PYTHON ?= python3

.PHONY: install data app test lint

install:
	$(PYTHON) -m pip install -e .

data:
	$(PYTHON) scripts/run_pipeline.py

app:
	$(PYTHON) -m streamlit run app/streamlit_app.py

test:
	$(PYTHON) -m pytest

lint:
	$(PYTHON) -m ruff check .
