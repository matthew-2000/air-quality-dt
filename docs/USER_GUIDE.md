# Guida Utente

La dashboard mostra le misure reali piu' recenti dei sensori UNISA sul campus.

## Cosa vedi

- **Copertura per inquinante**: quanti sensori stanno contribuendo allo snapshot operativo.
- **Mappa campus**: superficie interpolata, marker sensori e vista copertura.
- **Dettaglio sensore**: ultima misura disponibile, freschezza del dato e storico recente.
- **Stato ingestione**: quanti dati sono disponibili e se il feed live e' attivo, stale o non configurato.

## Inquinanti disponibili

- PM1
- PM2.5
- PM10
- indice VOC
- indice NOx

## Interpretazione corretta

- I marker sono misure reali dei sensori.
- La superficie mappa e' una lettura spaziale interpolata, non una misura certificata in ogni punto del campus.
- Il timestamp operativo rappresenta uno snapshot costruito con bucket da 1 minuto e finestra di freschezza configurata.

## Feed live

La dashboard espone chiaramente lo stato del feed:

- `live`: il broker MQTT sta alimentando dati recenti
- `stale`: i dati esistono, ma l'ultima ricezione non e' recente
- `unconfigured`: mancano variabili MQTT locali

Per aggiornare il feed:

```bash
make ingest-live MQTT_DURATION=30 MQTT_INTERVAL=5
```

oppure avvia tutto insieme:

```bash
make dev-live MQTT_DURATION=30 MQTT_INTERVAL=5
```

## Limiti

Il cockpit e' uno strumento operativo e di osservazione. Non e' un sistema ufficiale per decisioni sanitarie, legali o regolatorie.
