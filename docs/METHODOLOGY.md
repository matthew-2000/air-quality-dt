# Metodologia

## Obiettivo

Il Digital Twin usa misure reali dei sensori UNISA per mostrare lo stato ambientale del campus e costruire mappe operative in tempo quasi reale.

## Ingestione

La sorgente operativa è un broker MQTT configurato tramite variabili d'ambiente. Ogni messaggio contiene un ID sensore, un timestamp e misure ambientali. La pipeline conserva anche il timestamp di ricezione del messaggio.

Campi normalizzati:

- `pm1`
- `pm25`
- `pm10`
- `voc_index`
- `nox_index`
- `temperature`
- `humidity`
- `num_devices_sniffed`

Le coordinate arrivano dal catalogo locale dei sensori, che contiene gli ID dei sensori fisici e la loro posizione.

## Dataset Processati

La build produce:

- `campus_real_sensors.geojson` per la mappa sensori.
- `real_sensor_metadata.parquet` per i metadata.
- `real_sensor_observations.parquet` per le osservazioni reali normalizzate.
- `campus_air_quality_estimates.parquet` come tabella compatibile con API e UI.
- `realtime_ingestion_summary.json` per audit rapido dell'ultima ingestione.

## Mappa

I punti sulla mappa sono sensori fisici. La heatmap è una superficie interpolata dai valori misurati dai sensori, utile per leggere pattern spaziali. Non va interpretata come misura continua certificata in ogni punto del campus.

## Scenari

Gli scenari what-if non modificano il dato reale. Partono dalla misura del sensore e applicano coefficienti trasparenti per simulare riduzione traffico, vento, pioggia o miglioramento green.

Il proxy traffico usa `num_devices_sniffed`, normalizzato in `traffic_index`.

## Qualità Dati

Ogni riga conserva:

- timestamp misurato;
- timestamp di ricezione;
- sensore;
- sorgente;
- coordinate;
- confidence label.

I dati sono reali, ma il sistema non è un servizio sanitario o regolatorio ufficiale.
