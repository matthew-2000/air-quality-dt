# Metodologia

## Obiettivo

Il Digital Twin mostra lo stato ambientale del campus usando misure reali dei sensori UNISA e snapshot operativi quasi realtime.

## Pipeline dati

La pipeline attuale e' questa:

1. ingestione MQTT dal broker configurato via `.env` o `.env.local`
2. normalizzazione dei messaggi in osservazioni sensore
3. scrittura nello store operativo SQLite
4. generazione degli artifact usati da dashboard e audit

## Store operativo

La sorgente primaria del cockpit e' il database SQLite:

- `data/processed/realtime_operational.db`

Contiene almeno:

- catalogo sensori
- messaggi raw MQTT
- osservazioni normalizzate
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
- indicatori di freschezza e copertura

## Analytics Sprint 2

Il livello analytics aggiunge tre letture sopra lo snapshot operativo:

- qualita' dato, con flag per valori mancanti, range anomali, latenze e timestamp incoerenti
- aggregazione per zone campus, usando i poligoni statici di `campus_zones.geojson`
- trend recente per inquinante, calcolato sui bucket temporali disponibili

Queste metriche non sostituiscono la misura raw. Servono a rendere il Digital Twin piu' utile per analisi operative: capire dove il segnale e' affidabile, quali zone hanno valori piu' alti e quanto il trend recente e' stabile.

L'endpoint `/api/analytics` restituisce qualita' complessiva, riepilogo zone, GeoJSON colorato delle zone e serie temporale recente per l'inquinante selezionato.

## Limiti

- MQTT non offre da solo uno storico completo.
- La superficie mappa e' interpolata dai sensori e va letta come supporto operativo.
- La dashboard oggi usa polling HTTP; non usa ancora SSE o WebSocket.
