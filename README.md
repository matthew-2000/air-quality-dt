# UNISA Air Quality Digital Twin

Cockpit React + API FastAPI per monitorare i sensori reali UNISA sul Campus di Fisciano.

Oggi il prodotto attivo e supportato e' questo:

- frontend React in `web/`
- API FastAPI in `api/`
- job dati, ingestione MQTT e store operativo in `src/unisa_air_twin/`
- motore what-if non distruttivo, forecast breve termine e decision support via dashboard

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

Il flusso prodotto non richiede comandi terminale per l'utente finale. La dashboard include la sezione **Gestione dati** e usa questi job API:

- `POST /api/jobs/context`: aggiorna sensori, zone e layer campus.
- `POST /api/jobs/snapshots`: rilegge lo storico MQTT raw e ricostruisce il dataset operativo.
- `POST /api/jobs/refresh`: ricostruisce gli snapshot dallo store operativo.
- `POST /api/jobs/enrich`: aggiorna fonti gratuite esterne e arricchisce osservazioni/snapshot.
- `GET /api/jobs`: mostra stato, errori e risultato delle operazioni avviate.
- `GET /api/sources`: mostra salute, cache e provenance delle fonti dati.
- `GET /api/export/{observations|sensors|raw-messages}?format=csv|json`: scarica dati disponibili.
- `GET /api/forecast`: previsioni operative 30/60/180 minuti.
- `POST /api/scenarios/run`: crea un run what-if salvato senza modificare osservazioni reali.
- `GET /api/scenarios/runs`: storico run salvati.
- `GET /api/decision-support`: alert, spiegazioni e "cosa fare ora".
- `GET /api/ops/health`: stato API, DB, MQTT, jobs, stream, export e backup.

Gli script in `scripts/` restano utility di sviluppo e compatibilita', ma non sono il percorso utente primario.

## Fonti dati

Il digital twin usa una provenance esplicita per ogni fonte:

- sensori UNISA via MQTT configurato localmente;
- OpenStreetMap per verde, viabilita' ed edifici campus;
- Open-Meteo Weather per vento, pioggia e meteo operativo;
- Open-Meteo Air Quality per background PM/NO2/O3/AQI.

Le risposte Open-Meteo sono salvate in `data/raw/external/` e riusate come cache se la rete non e' disponibile.

## Avvio App

### Deploy demo/produzione locale

```bash
make deploy
```

Equivalente:

```bash
docker compose up --build
```

Avvia API su `http://127.0.0.1:8000` e dashboard su `http://127.0.0.1:5173`, con healthcheck e restart policy.

L'API avvia automaticamente ingest MQTT se `.env.local` contiene le credenziali. Ogni ciclo ascolta MQTT, aggiorna store operativo, ricostruisce snapshot e notifica la dashboard via SSE.

### Modalita' consigliata: API + frontend insieme

```bash
make dev
```

Avvia:

- API su `http://127.0.0.1:8000`
- frontend su `http://127.0.0.1:5173`

Anche in sviluppo l'ingest automatico parte dentro API quando MQTT e' configurato.

## Pulizia workspace

Per rimuovere cache Python e build frontend:

```bash
make clean
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

Build frontend:

```bash
make build
```

## Flusso operativo consigliato

Per preparare una macchina nuova:

1. clona il repository;
2. esegui `make bootstrap`;
3. crea `.env.local` da `.env.example`;
4. inserisci password MQTT;
5. avvia `make dev` oppure `make deploy`.

La dashboard resta il centro operativo: i job manuali servono solo per refresh forzati o riparazioni, non per avvio ordinario.

## Output principali

- `data/processed/realtime_operational.db`
- `data/processed/campus_real_sensors.geojson`
- `data/processed/real_sensor_metadata.parquet`
- `data/processed/real_sensor_observations.parquet`
- `data/processed/campus_air_quality_estimates.parquet`
- `data/processed/realtime_ingestion_summary.json`

## Note operative

- MQTT non e' uno storico completo: ricevi i messaggi mentre il client e' connesso, piu' eventuali retained.
- Ingest MQTT automatico: `UNISA_AQDT_AUTO_INGEST=true`, durata ciclo `UNISA_AQDT_AUTO_INGEST_DURATION`, pausa `UNISA_AQDT_AUTO_INGEST_INTERVAL`.
- Il backend usa lo store SQLite operativo come sorgente primaria per la dashboard.
- Le fonti esterne gratuite sono cache-first: un errore rete non blocca la dashboard se esiste cache locale.
- Gli export CSV/JSON sono generati dall'API a partire dallo store operativo.
- Il frontend riceve aggiornamenti live via SSE dall'API e ricarica summary, mappa, analytics e dettaglio quando l'ingestione notifica un nuovo snapshot operativo.
- Se `EventSource` non e' disponibile nel browser, il frontend mantiene un fallback a polling HTTP ogni 60 secondi.
