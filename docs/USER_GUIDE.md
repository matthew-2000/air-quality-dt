# Guida Utente

Questa dashboard mostra misure reali dei sensori UNISA sul campus.

## Panoramica

Usa la barra laterale per scegliere metrica e timestamp. La mappa mostra i sensori fisici disponibili e una heatmap interpolata dai valori misurati.

Metriche disponibili:

- PM1
- PM2.5
- PM10
- indice VOC
- indice NOx

## Mappa

I marker rappresentano sensori reali. I colori più caldi indicano valori più alti per la metrica selezionata. La heatmap aiuta a leggere la distribuzione spaziale, ma non sostituisce la misura puntuale dei sensori.

## Scenari

Gli slider applicano scenari what-if sopra il dato reale selezionato. Servono per confrontare alternative operative, non per riscrivere le misure dei sensori.

## Serie Temporali

La sezione serie temporali mostra l'andamento di una metrica per un sensore reale.

## Aggiornamento Live

Il catalogo sensori e' incluso nel repository in `config/sensors/sensor_PEDT.json`.

Per raccogliere nuovi messaggi dal broker, crea `.env.local` da `.env.example`, inserisci la password MQTT e poi avvia l'ingestione:

```bash
make ingest-live MQTT_DURATION=30 MQTT_INTERVAL=5
```

Poi aggiorna API/UI o usa il pulsante di refresh.

## Limiti

Il progetto mostra dati reali e scenari esplorativi. Non è un sistema ufficiale per decisioni sanitarie, legali o regolatorie.
