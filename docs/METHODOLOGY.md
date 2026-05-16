# Metodologia

## Obiettivo

Il Digital Twin mostra lo stato ambientale del campus usando misure reali dei sensori UNISA e snapshot operativi quasi realtime.

## Pipeline dati

La pipeline attuale e' questa:

1. ingestione MQTT dal broker configurato via `.env` o `.env.local`
2. aggiornamento fonti gratuite esterne quando richiesto dalla dashboard
3. normalizzazione dei messaggi in osservazioni sensore
4. arricchimento con meteo, background aria, pressione traffico e verde OSM
5. pubblicazione eventi osservazione su event log append-only
6. materializzazione read model operativo tramite projector
7. generazione degli artifact usati da dashboard e audit

## Store operativo

La sorgente primaria del cockpit e' lo store operativo configurato:

- `data/processed/realtime_operational.db` quando il backend attivo e' `sqlite`

Backend disponibile oggi:

- `sqlite` per sviluppo/demo
- `postgres` come backend target per runtime piu' seri

Contiene almeno:

- catalogo sensori
- messaggi raw MQTT
- osservazioni normalizzate
- componenti di arricchimento e provenance
- metadata dell'ultimo export

I parquet e i json processati restano output secondari per compatibilita', export e ispezione.

## Snapshot operativo

Lo snapshot non e' evento-per-evento puro. E' un aggregato costruito con:

- bucket temporale di 1 minuto
- finestra di freschezza configurata
- ultima misura valida per sensore all'interno della finestra

Questo approccio produce una vista stabile e leggibile per il cockpit, mantenendo il sistema vicino al realtime senza richiedere un canale push dedicato.

## Dati mostrati

Per ogni riga operativa il sistema conserva:

- timestamp della misura
- timestamp di ricezione
- sensore
- coordinate
- inquinante
- valore stimato/base
- metriche ambientali accessorie
- componenti traffico, verde, vento, pioggia e background esterno
- indicatori di freschezza e copertura

## Fonti e Arricchimento

Il sistema usa fonti gratuite con cache locale e stato esplicito:

- OpenStreetMap: contesto campus, verde, strade, edifici
- Open-Meteo Weather: vento, precipitazione e meteo operativo
- Open-Meteo Air Quality: background PM10, PM2.5, NO2, O3 e AQI europeo

Il valore `base_value` resta la misura sensore normalizzata. Il valore `estimated_value` applica componenti modellistiche leggere basate su traffico osservato dal payload, verde OSM, vento e pioggia. Ogni riga conserva anche `background_value`, `background_source`, `source_url` e `uncertainty_score`.

Le fonti sono esposte da `/api/sources`. Gli export sono esposti da `/api/export/{dataset}`.

## Analytics

Il livello analytics aggiunge tre letture sopra lo snapshot operativo:

- qualita' dato, con flag per valori mancanti, range anomali, latenze e timestamp incoerenti
- aggregazione per zone campus, usando i poligoni statici di `campus_zones.geojson`
- trend recente per inquinante, calcolato sui bucket temporali disponibili

Queste metriche non sostituiscono la misura raw. Servono a rendere il Digital Twin piu' utile per analisi operative: capire dove il segnale e' affidabile, quali zone hanno valori piu' alti e quanto il trend recente e' stabile.

L'endpoint `/api/analytics` restituisce qualita' complessiva, riepilogo zone, GeoJSON colorato delle zone e serie temporale recente per l'inquinante selezionato.

## Realtime

Il runtime usa stream SSE:

- l'API espone uno stream SSE che osserva lo stato dello snapshot operativo
- il projector pubblica notifiche realtime via Redis quando materializza nuovi snapshot
- l'API puo' rilevare cambi anche dal versionamento persistito dell'event log
- il frontend React si sottoscrive allo stream e ricarica i pannelli quando riceve una notifica con un nuovo fingerprint del dataset live
- il refresh manuale resta disponibile per forzare una nuova esportazione degli artifact operativi

Questo modello evita il polling fisso come meccanica primaria della UI. La connessione SSE resta aperta con heartbeat, mentre i cambi reali arrivano da notifiche del projector o dalla verifica del versionamento persistito.

## Limiti

- MQTT non offre da solo uno storico completo.
- La superficie mappa e' interpolata dai sensori e va letta come supporto operativo.
- Lo stream live usa SSE e non WebSocket: e' adeguato al flusso server-to-client del cockpit, ma non abilita input realtime bidirezionale.
