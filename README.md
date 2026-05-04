# UNISA Air Quality Digital Twin

Cockpit React + API FastAPI per monitorare i sensori reali UNISA sul Campus di Fisciano.

Oggi il prodotto attivo e supportato e' questo:

- frontend React in `web/`
- API FastAPI in `api/`
- ingestione MQTT e dataset operativi in `scripts/` e `src/unisa_air_twin/`

Il vecchio ramo Streamlit e la simulazione scenario non fanno piu' parte dell'app corrente.

## Requisiti

- `python3.11` o superiore
- `node` 20+ con `npm`

## Setup

Bootstrap completo dalla root:

```bash
make bootstrap
```

Equivalente manuale:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .
npm --prefix web install
```

## Configurazione MQTT

Per ricevere dati live servono le credenziali del broker MQTT.

Il progetto legge automaticamente `.env` e `.env.local` nella root del repository. Il file consigliato per i secret locali e' `.env.local`.

Parti da:

```bash
cp .env.example .env.local
```

Poi completa la password:

```dotenv
UNISA_MQTT_HOST=square.sensesquare.eu
UNISA_MQTT_PORT=1883
UNISA_MQTT_USERNAME=pedt
UNISA_MQTT_PASSWORD=...
UNISA_MQTT_TOPIC="#"
```

## Dati

### Solo layer campus

```bash
python3 scripts/download_data.py
```

oppure:

```bash
make data
```

`make data` costruisce anche i dataset locali disponibili.

### Un giro di ingest live

```bash
make data-live
```

Durata personalizzata:

```bash
make data-live MQTT_DURATION=180
```

### Ingestione continua

```bash
make ingest-live MQTT_DURATION=30 MQTT_INTERVAL=5
```

## Avvio App

### Modalita' consigliata: API + frontend insieme

```bash
make dev
```

Avvia:

- API su `http://127.0.0.1:8000`
- frontend su `http://127.0.0.1:5173`

### Modalita' live completa: API + frontend + ingestione continua

```bash
make dev-live MQTT_DURATION=30 MQTT_INTERVAL=5
```

Questa modalita' richiede le variabili MQTT configurate.

## Pulizia workspace

Per rimuovere cache Python e build frontend:

```bash
make clean
```

Per eliminare gli screenshot temporanei di QA UI:

```bash
make clean-ui
```

### Avvio separato

API:

```bash
make api
```

Frontend:

```bash
make web
```

## Flusso operativo consigliato

Per preparare una macchina nuova:

1. clona il repository;
2. esegui `make bootstrap`;
3. crea `.env.local` da `.env.example`;
4. esegui `make data-live`;
5. avvia `make dev`.

Per sviluppo con feed live continuo:

1. verifica `.env.local`;
2. esegui `make dev-live`.

## Output principali

- `data/processed/realtime_operational.db`
- `data/processed/campus_real_sensors.geojson`
- `data/processed/real_sensor_metadata.parquet`
- `data/processed/real_sensor_observations.parquet`
- `data/processed/campus_air_quality_estimates.parquet`
- `data/processed/realtime_ingestion_summary.json`

## Note operative

- MQTT non e' uno storico completo: ricevi i messaggi mentre il client e' connesso, piu' eventuali retained.
- Il backend usa lo store SQLite operativo come sorgente primaria per la dashboard.
- Il frontend aggiorna lo stato via HTTP; il feed e' near-real-time, non push realtime via WebSocket/SSE.
