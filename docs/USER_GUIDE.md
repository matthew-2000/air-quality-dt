# Guida Utente

La dashboard mostra le misure reali piu' recenti dei sensori UNISA sul campus.

## Cosa vedi

- **Copertura per inquinante**: quanti sensori stanno contribuendo allo snapshot operativo.
- **Mappa campus**: superficie interpolata, marker sensori e vista copertura.
- **Twin analytics**: qualita' del dato, trend campus e riepilogo delle zone operative.
- **Scenari**: simulazioni what-if salvabili che confrontano baseline reale e scenario senza cambiare i dati reali.
- **Forecast**: previsione operativa a 30, 60 e 180 minuti con bande di incertezza e rischio stimato.
- **Decision support**: alert, spiegazioni e azioni consigliate in linguaggio non tecnico.
- **Dettaglio sensore**: ultima misura disponibile, freschezza del dato e storico recente.
- **Stato ingestione**: quanti dati sono disponibili e se il feed live e' attivo, stale o non configurato.
- **Gestione dati**: operazioni per aggiornare contesto, ricostruire dataset e aggiornare snapshot senza usare terminale.
- **Fonti dati**: stato di OpenStreetMap, Open-Meteo Weather e Open-Meteo Air Quality.

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
- La qualita' dato segnala problemi operativi del flusso, per esempio valori mancanti, ritardi di arrivo o misure fuori range.
- Le zone operative aggregano i sensori disponibili nell'area: sono utili per confronto e priorita', non per certificare ogni punto del campus.

## Feed live

La dashboard espone chiaramente lo stato del feed e si riallinea in automatico via stream SSE quando arriva un nuovo snapshot operativo.

Stati feed:

- `live`: il broker MQTT sta alimentando dati recenti
- `stale`: i dati esistono, ma l'ultima ricezione non e' recente
- `unconfigured`: mancano variabili MQTT locali

Se il browser non supporta SSE, la UI torna automaticamente a un polling HTTP periodico.

Per aggiornare i dati dalla UI usa **Gestione dati**:

- **Aggiorna snapshot**: ricalcola la vista operativa dai dati gia' acquisiti.
- **Ricostruisci dataset**: normalizza lo storico MQTT raw e rigenera gli snapshot.
- **Aggiorna contesto**: aggiorna sensori, zone e layer campus.
- **Arricchisci fonti**: aggiorna meteo, qualita' aria esterna, verde e componenti del modello.

Quando un job cambia i dati, la dashboard ricarica summary, mappa, analytics e dettaglio.

## Scenari what-if

Gli scenari non modificano osservazioni, snapshot o storico reale. Ogni simulazione crea un run salvato con:

- baseline usata;
- tipo scenario e intensita';
- delta medio per inquinante;
- variazione per zone;
- confidence;
- rischio stimato;
- driver principali;
- aree e sensori da monitorare.

Scenari disponibili: aumento traffico, riduzione traffico, evento campus, chiusura parcheggio, nuovo sensore, sensore offline, pioggia, vento, aumento verde e variazione finestra freschezza.

## Decisioni operative

La sezione **Cosa fare ora** sintetizza:

- livello rischio previsto;
- alert attivi;
- zone da controllare;
- possibili cause;
- suggerimenti per posizionamento sensori;
- spiegazione di confidence, anomalie, forecast e delta scenario.

Se mancano dati, la UI propone azioni interne: aggiornare snapshot, avviare job dati o creare uno scenario what-if salvato.

## Download dati

La sezione **Gestione dati** espone download diretti:

- osservazioni normalizzate in CSV;
- catalogo sensori in JSON;
- messaggi MQTT raw in CSV.

## Limiti

Il cockpit e' uno strumento operativo e di osservazione. Non e' un sistema ufficiale per decisioni sanitarie, legali o regolatorie.
