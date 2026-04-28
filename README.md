# UNISA Air Quality Digital Twin - MVP

This project is a first working prototype of an Urban Digital Twin for air quality around the University of Salerno, Campus di Fisciano.

It downloads public data where possible, prepares geospatial and time-series datasets, creates virtual campus sensors, estimates local air quality from nearby ARPAC stations plus simple weather and mobility proxies, and exposes an interactive Streamlit dashboard.

## Why this is a Digital Twin MVP

The MVP links a physical place (UNISA Fisciano campus) with a live-ish data representation:

- campus context from OpenStreetMap;
- official regional air-quality data from ARPAC Campania Open Data;
- weather from the UNISA weather page when discoverable, otherwise Open-Meteo fallback;
- virtual sensors placed around meaningful campus zones;
- a transparent estimation model and scenario controls.

It is intentionally simple: no Kubernetes, no microservices, no PostGIS, no game engine, and no complex 3D.

## Data sources

- ARPAC Campania Open Data portal: <https://dati.arpacampania.it/>
- ARPAC hourly raw air quality: <https://dati.arpacampania.it/dataset/dati-grezzi-orari-qualita-aria>
- ARPAC validated daily air quality: <https://dati.arpacampania.it/dataset/dati-rqa-giornalieri-validati>
- ARPAC historical monitoring: <https://dati.arpacampania.it/dataset/dati-monitoraggio-qualita-aria>
- ARPAC station metadata: <https://dati.arpacampania.it/dataset/rete-di-monitoraggio-della-qualita-dell-aria>
- UNISA weather reference page: <https://web.unisa.it/servizi-on-line/stazione-meteo>
- Open-Meteo fallback for Fisciano coordinates: latitude `40.771`, longitude `14.790`
- OpenStreetMap via OSMnx for campus buildings, roads, green areas, parking, and transport points
- UNISA campus map reference for names/POIs: <https://web.unisa.it/vivere-il-campus/unisa-experience/campus-map>

The downloader first tries CKAN `package_show` endpoints for ARPAC datasets, then scrapes dataset HTML pages for resource links. Raw files are cached under `data/raw/arpac/` and are not downloaded again unless `--force` is passed.

## Installation

Python 3.11+ is required.

```bash
python3 -m pip install -e .
```

or:

```bash
make install
```

If your system provides `python` instead of `python3`, run:

```bash
make PYTHON=python install
```

## How to run

Run the full pipeline:

```bash
python scripts/run_pipeline.py
```

If your shell does not have a `python` command, use:

```bash
python3 scripts/run_pipeline.py
```

Start the dashboard:

```bash
streamlit run app/streamlit_app.py
```

If the `streamlit` executable is not on your `PATH`, use the equivalent module form:

```bash
python3 -m streamlit run app/streamlit_app.py
```

Useful Make commands:

```bash
make data
make app
make test
make lint
```

## Expected outputs

Processed outputs are written under `data/processed/`:

- `air_quality_observations.parquet`
- `arpac_station_metadata.parquet`
- `weather_hourly.parquet`
- `campus_buildings.geojson`
- `campus_roads.geojson`
- `campus_green.geojson`
- `campus_transport.geojson`
- `campus_parking.geojson`
- `campus_virtual_sensors.geojson`
- `campus_air_quality_estimates.parquet`
- `schema_report.json` when schema warnings occur

All processed tables include provenance fields where applicable:

- `source`
- `source_url`
- `downloaded_at`
- `is_synthetic`

If a public source cannot be downloaded or parsed, the pipeline creates a clearly labeled `source="synthetic_fallback"` dataset so the dashboard still runs after a clean clone. The code never silently fakes official measurements.

## Dashboard

The dashboard title is:

> UNISA Air Quality Digital Twin - MVP

Sections:

- Overview: explanation, data sources, and official-use disclaimer.
- Map: virtual campus sensors and nearby ARPAC stations where coordinates exist.
- Time series: pollutant and sensor selectors.
- Scenario what-if: traffic reduction, wind multiplier, rain-event controls.
- Data quality: download/model metadata, row counts, station counts, schema warnings.

## Model

The estimation model is deliberately transparent:

```text
estimated_value =
    inverse_distance_weighted_ARPAC_base
    + traffic_factor * traffic_index
    - green_factor * green_index
    + weather_adjustment
```

Traffic, green, wind, and rain coefficients are configured in `config/settings.yaml`.

## Limitations

This is a demonstrative MVP, not an official health or regulatory model. It does not replace ARPAC measurements. Virtual sensor coordinates are synthetic unless explicitly improved later. Weather fallback uses Open-Meteo when the UNISA page does not expose a reliable machine-readable endpoint. The atmospheric model is intentionally simple and should be validated before any scientific or operational use.

## Next steps

- Add real low-cost sensors on campus.
- Validate estimates against ARPAC observations.
- Add MQTT ingestion for streaming sensor data.
- Add an NGSI-LD-compatible entity model.
- Use PostGIS/TimescaleDB later when the prototype grows.
- Improve the atmospheric and dispersion model.
