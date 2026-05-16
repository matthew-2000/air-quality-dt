# Operations

## Deploy

Avvio locale deploy-ready:

```bash
make deploy
```

Equivalente:

```bash
docker compose up --build
```

Servizi:

- API FastAPI: `http://127.0.0.1:8000`
- Projector worker: processo separato per materializzare proiezioni
- Redis: bridge pub/sub realtime cross-process
- Dashboard React: `http://127.0.0.1:5173`

Compose abilita healthcheck e `restart: unless-stopped`.

All'avvio API puo' partire ingest MQTT automatico se le variabili `UNISA_MQTT_*` sono complete. Il projector gira come worker separato nel compose e aggiorna le proiezioni operative.

## Render Free

Per demo affidabili su Render conviene usare un solo Web Service Docker:

- `Dockerfile.api` builda anche il frontend React;
- FastAPI serve sia `/api/*` sia la dashboard SPA;
- `data/` viene incluso nell'immagine come dataset demo seed;
- `render.yaml` imposta `UNISA_AQDT_AUTO_INGEST=false` per evitare failure o rumore quando MQTT non e' configurato.
- il live MQTT e' esposto come job manuale one-shot, pensato per demo su macchine con poche risorse.

Con questa configurazione, un restart o un redeploy di Render riparte sempre da uno stato dimostrabile e consistente, pur restando su filesystem effimero.

Per mostrare il live senza destabilizzare il web service:

1. configura `UNISA_MQTT_*` nel servizio Render;
2. lascia `UNISA_AQDT_AUTO_INGEST=false`;
3. dalla sezione **Gestione dati** usa il comando **Ascolta live 10s**;
4. attendi il completamento del job e il refresh della dashboard.

## Configurazione

Variabili MQTT in `.env.local` o ambiente:

- `UNISA_MQTT_HOST`
- `UNISA_MQTT_PORT`
- `UNISA_MQTT_USERNAME`
- `UNISA_MQTT_PASSWORD`
- `UNISA_MQTT_TOPIC`

La dashboard mostra se MQTT e' configurato e segnala feed stale o non configurato.

Controlli ingest:

- `UNISA_AQDT_AUTO_INGEST=true|false`
- `UNISA_AQDT_AUTO_INGEST_DURATION=30`
- `UNISA_AQDT_AUTO_INGEST_INTERVAL=10`
- `UNISA_AQDT_AUTO_PROJECTOR=true|false`
- `UNISA_AQDT_PROJECTOR_INTERVAL=2`
- `UNISA_AQDT_PROJECTOR_BATCH_SIZE=500`
- `UNISA_AQDT_PROJECTOR_MAX_RETRIES=3`
- `UNISA_AQDT_EVENT_BUS_BACKEND=store|kafka`
- `UNISA_AQDT_KAFKA_BOOTSTRAP_SERVERS=localhost:9092`
- `UNISA_AQDT_KAFKA_CONSUMER_GROUP=aqdt-projector`
- `UNISA_AQDT_KAFKA_POLL_TIMEOUT_MS=1000`
- `UNISA_AQDT_REDIS_URL=redis://...`
- `UNISA_AQDT_REDIS_CHANNEL=aqdt:snapshots`

Flusso runtime:

1. ingest ascolta MQTT;
2. salva raw messages e pubblica envelope eventi osservazione versionati nello store operativo;
3. event bus selector usa backend `store` o `kafka` per esporre stream consumabile;
4. projector consuma stream eventi per topic logico e materializza `observations` e `operational_snapshots`;
5. projector pubblica notifica realtime envelope `snapshots.materialized`;
6. API riceve notifica Redis o rileva cambio persistito;
7. dashboard riceve update via SSE.

Contratto minimo evento:

- `event_name`
- `topic`
- `schema_version`
- `producer`
- `occurred_at`
- `aggregate_type`
- `aggregate_id`
- `partition_key`
- `payload`

Policy projector:

- errore retriable: evento resta davanti al cursore, retry count persistito
- poison event: dopo `UNISA_AQDT_PROJECTOR_MAX_RETRIES` viene parcheggiato in DLQ locale
- audit DLQ: evento `projection.dead_lettered` su topic `aqdt.dlq`
- health operativo: servizio `Projector` mostra retry e DLQ attivi

## Release Gate

Prima di stage o commit esegui sempre:

```bash
ruff check .
pytest -q
```

Se usi runtime separato in locale, verifica anche:

1. `make api`
2. `make projector`
3. `make web`
4. apertura dashboard e refresh live senza errori in `GET /api/ops/health`

## Health

Endpoint: `GET /api/ops/health`

Controlla:

- API;
- DB operativo;
- MQTT;
- jobs;
- stream SSE;
- export;
- stato backup manuale.

La stessa informazione appare nella sezione **Health dashboard**.

## Backup operativo

Il volume `./data:/app/data` contiene store operativo, raw e processed artifacts. Backup minimo:

1. snapshot periodico della directory `data/`;
2. restore test su ambiente non produttivo;
3. verifica `GET /api/health` e apertura dashboard.

Nota: non esiste ancora un job automatico di backup/retention. La dashboard mostra lo stato come manuale/non configurato per non dichiarare automazioni assenti.

## Troubleshooting

- Feed live assente: controlla stato MQTT nella dashboard, poi variabili ambiente.
- Dati vecchi: verifica job `auto_ingest_mqtt`; poi usa **Aggiorna snapshot** o **Ricostruisci dataset** solo come recupero manuale.
- Fonti esterne fallite: usa **Arricchisci fonti**; se rete assente, cache esistente resta utilizzabile.
- Export vuoto: verifica osservazioni e raw messages in **Data Center**.
- Stream non aggiornato tra processi: verifica `UNISA_AQDT_REDIS_URL`, stato Redis e worker `projector`.
- Projector bloccato: controlla `GET /api/ops/health`, poi summary `projection_failures` e valore `UNISA_AQDT_PROJECTOR_MAX_RETRIES`.
