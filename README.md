# UNISA Air Quality Digital Twin

Dashboard e API per leggere dati reali dai sensori fisici UNISA sul Campus di Fisciano.

Il repository contiene la configurazione ripetibile non segreta: catalogo sensori, host MQTT, porta, username e topic. La password resta fuori da git e va impostata in `.env.local` o tramite secret manager.

## Setup Su Un Nuovo PC

Prerequisiti minimi:

- `python3.11` o superiore
- `node` 20+ con `npm`

Bootstrap iniziale dalla root del repository:

```bash
make bootstrap
```

Se non usi `make`:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
npm --prefix web install
```

## Dati E Configurazione

Questo progetto usa quattro sorgenti diverse. Vanno tenute separate:

1. layer geografici campus da OpenStreetMap;
2. catalogo sensori PEDT versionato nel repo;
3. credenziali MQTT per ingestione live.
4. raw MQTT generati localmente dall'ingestione.

### 1. Layer Campus Da Scaricare

I layer OSM non vanno copiati dal vecchio PC. Li costruisce il progetto quando esegui:

```bash
python3 scripts/download_data.py
```

oppure:

```bash
make data
```

`make data` fa di piu': scarica o riusa i layer campus, genera le zone e prova anche a costruire i dataset a partire dai raw locali.

Se OpenStreetMap non e' raggiungibile, [src/unisa_air_twin/osm.py](/Users/matteoercolino/IdeaProjects/air-quality-dt/src/unisa_air_twin/osm.py) genera layer fallback minimi in `data/processed/`.

### 2. Catalogo Sensori

Il catalogo sensori PEDT e' versionato in:

- `config/sensors/sensor_PEDT.json`

La pipeline lo usa tramite `config/settings.yaml`, quindi non serve copiare file da `Downloads` o da altri PC.

### 3. Variabili MQTT Per Il Live

Le credenziali MQTT servono per raccogliere nuovi messaggi dal broker con `scripts/ingest_mqtt.py`. Il progetto legge automaticamente `.env` e `.env.local` nella root del repository.

Crea `.env.local` partendo da `.env.example`:

```bash
cp .env.example .env.local
```

e compila solo la password:

```dotenv
UNISA_MQTT_HOST=square.sensesquare.eu
UNISA_MQTT_PORT=1883
UNISA_MQTT_USERNAME=pedt
UNISA_MQTT_PASSWORD=...
UNISA_MQTT_TOPIC="#"
```

`.env.local` e' ignorato da git.

### 4. Raw MQTT

I raw MQTT non si spostano tra PC. Ogni macchina li genera ascoltando il broker:

- `data/raw/live_sensors/mqtt_data.csv`
- `data/raw/live_sensors/mqtt_raw.jsonl`

Nota tecnica: MQTT non e' un database storico. Con topic `#` ricevi i messaggi pubblicati mentre il client e' connesso, piu' eventuali messaggi retained se il broker li espone. Se serve ricostruire mesi di storico, serve una sorgente storica dedicata, non il solo subscribe MQTT.

## Pipeline

Per preparare una macchina nuova l'ordine corretto e' questo:

1. clona il repo;
2. esegui `make bootstrap`;
3. crea `.env.local` con la password MQTT;
4. esegui `make data-live`.

Build dei dataset dai raw gia' raccolti:

```bash
python3 scripts/build_datasets.py
```

Pipeline completa dati + layer campus:

```bash
make data
```

Pipeline completa da broker MQTT:

```bash
make data-live
```

Di default ascolta il broker per 60 secondi. Puoi cambiare durata:

```bash
make data-live MQTT_DURATION=180
```

Solo layer geografici e metadati sensori:

```bash
python3 scripts/download_data.py
```

Ingestione live in cicli continui dal broker MQTT:

```bash
make ingest-live MQTT_DURATION=30 MQTT_INTERVAL=5
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

URL: `http://127.0.0.1:8000`

Cockpit React:

```bash
npm --prefix web run dev
```

URL tipico: `http://127.0.0.1:5173`

In sviluppo il frontend chiama `/api` e Vite inoltra le richieste a `http://127.0.0.1:8000`. In questo modo browser e API restano allineati senza configurare `VITE_API_BASE` su ogni PC.

Dashboard Streamlit legacy:

```bash
python3 -m streamlit run app/streamlit_app.py
```

URL tipico: `http://127.0.0.1:8501`

Per una macchina nuova, la sequenza pratica minima e' questa:

1. Clona il repo.
2. Esegui `make bootstrap`.
3. Crea `.env.local` da `.env.example` e inserisci la password.
4. Esegui `make data-live`.
5. Avvia API e frontend in due terminali separati con `make api` e `make web`.

## Real Time

L'app è predisposta per aggiornamenti live, ma servono due processi:

- un processo di ingestione MQTT continuo che ascolta il broker e aggiorna i parquet;
- API/UI attive, con refresh automatico o manuale dei dati.

La UI React interroga periodicamente l'API; per aggiornamenti push veri via WebSocket/SSE serve un ulteriore step architetturale.
