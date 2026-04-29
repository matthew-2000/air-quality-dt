# UNISA Air Quality Digital Twin

Dashboard e API per leggere dati reali dai sensori fisici UNISA sul Campus di Fisciano.

Il repository non contiene dettagli del broker MQTT, credenziali, topic operativi o nomi di provider. Tutte le informazioni di connessione devono arrivare da variabili d'ambiente o da secret manager.

## Configurazione Privata

Imposta le variabili d'ambiente fuori dal repository:

```bash
export UNISA_MQTT_HOST='...'
export UNISA_MQTT_PORT='...'
export UNISA_MQTT_USERNAME='...'
export UNISA_MQTT_PASSWORD='...'
export UNISA_MQTT_TOPIC='...'
```

I dati raw locali sono ignorati da git e vanno copiati sotto:

- `data/raw/live_sensors/sensor_catalog.json`
- `data/raw/live_sensors/mqtt_data.csv`
- `data/raw/live_sensors/mqtt_raw.jsonl`

## Pipeline

Build offline dai raw già raccolti:

```bash
python3 scripts/build_datasets.py
```

Ingestione live in cicli continui:

```bash
python3 scripts/ingest_mqtt.py --watch --duration 30 --interval 5
```

Output principali:

- `data/processed/campus_real_sensors.geojson`
- `data/processed/real_sensor_metadata.parquet`
- `data/processed/real_sensor_observations.parquet`
- `data/processed/campus_air_quality_estimates.parquet`
- `data/processed/realtime_ingestion_summary.json`

## Avvio

API FastAPI:

```bash
python3 -m uvicorn api.main:app --reload
```

Cockpit React:

```bash
npm --prefix web run dev
```

Dashboard Streamlit legacy:

```bash
python3 -m streamlit run app/streamlit_app.py
```

## Real Time

L'app è predisposta per aggiornamenti live, ma servono due processi:

- un processo di ingestione MQTT continuo che ascolta il broker e aggiorna i parquet;
- API/UI attive, con refresh automatico o manuale dei dati.

La UI React interroga periodicamente l'API; per aggiornamenti push veri via WebSocket/SSE serve un ulteriore step architetturale.
