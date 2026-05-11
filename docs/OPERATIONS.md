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
- Dashboard React: `http://127.0.0.1:5173`

Compose abilita healthcheck e `restart: unless-stopped`.

All'avvio API parte anche ingest MQTT automatico se le variabili `UNISA_MQTT_*` sono complete. Non serve piu' eseguire comandi dati separati per il flusso ordinario.

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

Ogni ciclo:

1. ascolta MQTT;
2. salva raw messages e osservazioni normalizzate;
3. ricostruisce snapshot operativi;
4. aggiorna summary/dashboard via SSE.

## Health

Endpoint: `GET /api/ops/health`

Controlla:

- API;
- DB operativo;
- MQTT;
- jobs;
- stream SSE;
- export;
- backup/retention.

La stessa informazione appare nella sezione **Health dashboard**.

## Backup e retention

Il volume `./data:/app/data` contiene store operativo, raw e processed artifacts. Backup minimo:

1. snapshot periodico della directory `data/`;
2. retention coerente con setting dashboard;
3. restore test su ambiente non produttivo;
4. verifica `GET /api/health` e apertura dashboard.

## Troubleshooting

- Feed live assente: controlla stato MQTT nella dashboard, poi variabili ambiente.
- Dati vecchi: verifica job `auto_ingest_mqtt`; poi usa **Aggiorna snapshot** o **Ricostruisci dataset** solo come recupero manuale.
- Fonti esterne fallite: usa **Arricchisci fonti**; se rete assente, cache esistente resta utilizzabile.
- Export vuoto: verifica osservazioni e raw messages in **Data Center**.
- Scenario non eseguibile: serve almeno un timestamp baseline disponibile.
