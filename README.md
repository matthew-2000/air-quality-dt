# UNISA Air Quality Digital Twin

Cockpit React + API FastAPI per monitorare i sensori reali UNISA sul Campus di Fisciano.

Oggi il prodotto attivo e supportato e' questo:

- frontend React in `web/`
- API FastAPI in `api/`
- job dati, ingestione MQTT e store operativo in `src/unisa_air_twin/`
- snapshot operativi, analytics osservativi, mappa campus, health ed export

Strato architetturale attuale:

- modular monolith con router HTTP separati in `api/routers/`
- read-model service in `src/unisa_air_twin/application/`
- pipeline ingest in `src/unisa_air_twin/ingestion/`
- costanti condivise in `src/unisa_air_twin/shared/`

Documentazione architetturale:

- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

Funzionalita' volutamente escluse dal perimetro attuale:

- scenari what-if salvati;
- forecast euristico breve termine;
- decision support testuale basato su regole deboli;
- registry asset/state/validation presentati come "twin core" senza modello fisico sufficiente.

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
- `POST /api/jobs/replay-projections`: rilegge event log append-only e ricostruisce le proiezioni operative.
- `GET /api/jobs`: mostra stato, errori e risultato delle operazioni avviate.
- `GET /api/sources`: mostra salute, cache e provenance delle fonti dati.
- `GET /api/export/{observations|sensors|raw-messages}?format=csv|json`: scarica dati disponibili.
- `GET /api/ops/health`: stato API, DB, MQTT, jobs, stream, export e backup manuale/non configurato.

Gli script in `scripts/` restano utility di sviluppo e compatibilita', ma non sono il percorso utente primario.

## Fonti dati

Il digital twin usa una provenance esplicita per ogni fonte:

- sensori UNISA via MQTT configurato localmente;
- OpenStreetMap per verde, viabilita' ed edifici campus;
- Open-Meteo Weather per vento, pioggia e meteo operativo;
- Open-Meteo Air Quality per background PM/NO2/O3/AQI.

Le risposte Open-Meteo sono salvate in `data/raw/external/` e riusate come cache se la rete non e' disponibile.

## Avvio App

### Deploy demo su Render Free

Il percorso piu' affidabile per demo su Render e' un singolo **Web Service** Docker che serve:

- API FastAPI
- dashboard React buildata e servita dalla stessa app
- dataset demo incluso nell'immagine

Nel repository c'e' gia' un blueprint minimo in `render.yaml` e la build usa `Dockerfile.api`.

Scelta operativa consigliata per demo:

- `UNISA_AQDT_AUTO_INGEST=false` su Render per evitare dipendenze live da MQTT;
- abilita le variabili `UNISA_MQTT_*` solo se vuoi davvero mostrare ingest live;
- per il live su Render free usa il job manuale **Ascolta live 10s** dalla dashboard invece di un loop permanente;
- ogni redeploy/ripartenza riparte dal dataset demo incluso nell'immagine, quindi lo stato resta coerente anche senza disco persistente.

### Deploy demo/produzione locale

```bash
make deploy
```

Equivalente:

```bash
docker compose up --build
```

Avvia API su `http://127.0.0.1:8000` e dashboard su `http://127.0.0.1:5173`, con healthcheck e restart policy.

L'API avvia automaticamente ingest MQTT se `.env.local` contiene le credenziali. Ogni ciclo ascolta MQTT e pubblica eventi osservazione nello store operativo; il worker `projector` materializza poi snapshot e read model, mentre API e Redis propagano il refresh realtime verso la dashboard via SSE.

Con `docker compose` ora partono anche:

- `projector`: worker separato che consuma event log e materializza proiezioni operative;
- `redis`: canale pub/sub per notifiche realtime cross-process.

### Modalita' consigliata: API + frontend insieme

```bash
make dev
```

Avvia:

- API su `http://127.0.0.1:8000`
- frontend su `http://127.0.0.1:5173`

Per sviluppo con worker proiezioni separato:

```bash
python scripts/dev_app.py --with-projector
```

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

Projector worker:

```bash
make projector
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

## Persistence backend

Backend default: `sqlite`.

Per usare PostgreSQL/PostGIS come store operativo primario:

```dotenv
UNISA_AQDT_PERSISTENCE_BACKEND=postgres
UNISA_AQDT_POSTGRES_DSN=postgresql://aqdt:aqdt@localhost:5432/aqdt
UNISA_AQDT_POSTGRES_SCHEMA=aqdt
```

La migration iniziale e' in:

- `src/unisa_air_twin/persistence/migrations/001_initial_postgres.sql`

Il layer applicativo continua a usare `unisa_air_twin.operational_store` come facade stabile, mentre l'implementazione concreta viene selezionata dal backend configurato.

## Event log operativo

Il sistema ora registra eventi persistenti nello store operativo:

- `observations.upserted`
- `observations.replaced`
- `snapshots.materialized`

Ogni evento usa ora envelope versionato bus-ready con campi minimi:

- `event_name`
- `topic`
- `schema_version`
- `producer`
- `occurred_at`
- `aggregate_type`
- `aggregate_id`
- `partition_key`
- `payload`

Topic logici attuali:

- `aqdt.observations`
- `aqdt.snapshots`
- `aqdt.dlq`

Backend bus attuale selezionabile:

- `store` default: projector legge da event log persistito locale
- `kafka` opzionale: fan-out producer + consumer seam Kafka/Redpanda-ready

Le proiezioni operative (`observations`, `operational_snapshots`) vengono ora materializzate da projector interno che consuma questo event log.

Questo rende il refresh realtime meno dipendente da memoria locale del processo API, abilita replay, e prepara passaggio successivo verso bus esterno (`Redis` / `Kafka` / `Redpanda`).

Il projector ora applica anche policy minima di resilienza:

- retry persistito per singolo `event_id`
- stop del cursore su errore retriable
- parking in DLQ locale dopo superamento `UNISA_AQDT_PROJECTOR_MAX_RETRIES`
- health summary con conteggi `retrying` e `dead_lettered`

Se `UNISA_AQDT_REDIS_URL` e' configurato:

- il projector pubblica notifiche realtime su Redis;
- l'API si sottoscrive al canale e sveglia subito lo stream SSE;
- piu' istanze API possono reagire allo stesso aggiornamento.

Se vuoi preparare backend bus esterno:

```dotenv
UNISA_AQDT_EVENT_BUS_BACKEND=kafka
UNISA_AQDT_KAFKA_BOOTSTRAP_SERVERS=localhost:9092
UNISA_AQDT_KAFKA_CONSUMER_GROUP=aqdt-projector
UNISA_AQDT_KAFKA_POLL_TIMEOUT_MS=1000
```

Per backend `kafka` serve dipendenza opzionale:

```bash
pip install '.[kafka]'
```

## Output principali

- `data/processed/realtime_operational.db` quando il backend attivo e' `sqlite`
- `data/processed/campus_real_sensors.geojson`
- `data/processed/real_sensor_metadata.parquet`
- `data/processed/real_sensor_observations.parquet`
- `data/processed/campus_air_quality_estimates.parquet`
- `data/processed/realtime_ingestion_summary.json`

## Quality Gate

Prima di stage o commit:

```bash
ruff check .
pytest -q
```

Questa e' la baseline minima per mantenere coerenti refactor architetturali, contratti API e projector/event log.

## Note operative

- MQTT non e' uno storico completo: ricevi i messaggi mentre il client e' connesso, piu' eventuali retained.
- Ingest MQTT automatico: `UNISA_AQDT_AUTO_INGEST=true`, durata ciclo `UNISA_AQDT_AUTO_INGEST_DURATION`, pausa `UNISA_AQDT_AUTO_INGEST_INTERVAL`.
- Su Render free e' consigliato tenere `UNISA_AQDT_AUTO_INGEST=false` e usare ingest manuale on-demand dalla dashboard.
- Il backend usa lo store operativo configurato come sorgente primaria per la dashboard.
- Le fonti esterne gratuite sono cache-first: un errore rete non blocca la dashboard se esiste cache locale.
- Gli export CSV/JSON sono generati dall'API a partire dallo store operativo.
- Il frontend riceve aggiornamenti live via SSE dall'API e ricarica summary, mappa, analytics e dettaglio quando il projector materializza un nuovo snapshot operativo.
- Se `EventSource` non e' disponibile nel browser, il frontend mantiene un fallback a polling HTTP ogni 60 secondi.
