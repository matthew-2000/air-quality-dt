# Metodologia tecnica

Questo documento descrive le scelte tecniche del MVP in modo comprensibile ma abbastanza preciso da poter essere discusso in una tesi o in una revisione progettuale.

## Obiettivo del modello

L'obiettivo non è produrre una previsione regolatoria, ma creare un prototipo riproducibile che combini:

- dati ufficiali disponibili pubblicamente;
- geografia del campus;
- sensori virtuali;
- proxy semplificati di traffico, verde e meteo;
- scenari what-if leggibili.

## Dati usati

### ARPAC

I dati ARPAC sono la fonte ufficiale regionale per la qualità dell'aria. Il downloader prova prima le API CKAN del portale, poi il parsing HTML delle pagine dataset.

Il sistema scarica solo le risorse più recenti per impostazione predefinita, così il progetto resta veloce e adatto a un MVP.

### Meteo

La pagina meteo UNISA viene ispezionata per cercare endpoint utilizzabili. Se non viene trovato un endpoint affidabile, il progetto usa Open-Meteo sulle coordinate di Fisciano/UNISA.

Variabili orarie:

- temperatura;
- umidità relativa;
- precipitazione;
- velocità del vento;
- direzione del vento.

### OpenStreetMap

OSMnx scarica layer GIS per:

- edifici;
- strade;
- aree verdi;
- trasporto pubblico;
- parcheggi.

Se OSM non è raggiungibile, il sistema genera GeoJSON fallback chiaramente marcati.

## Sensori virtuali

I sensori virtuali rappresentano luoghi significativi del campus:

- Rettorato;
- Edificio F;
- Terminal Bus;
- Parcheggio Multipiano;
- Mensa;
- Biblioteca Scientifica;
- Area Verde.

Le coordinate sono sintetiche ma deterministiche, collocate attorno al centro campus. Questo permette di avere una prima interfaccia GIS anche prima di installare sensori reali.

## Zone funzionali e entity model

Il MVP crea anche un layer `campus_zones.geojson` con poligoni sintetici per:

- mobilità;
- parcheggi;
- didattica;
- servizi;
- studio;
- verde;
- amministrazione.

Ogni zona include proprietà utili alla simulazione:

- `traffic_sensitivity`;
- `green_capacity`;
- descrizione;
- qualità della geometria.

Il file `digital_twin_entities.json` raccoglie zone e sensori virtuali come entità del Digital Twin. È una struttura semplice, pensata come primo passo verso modelli più interoperabili, per esempio NGSI-LD.

## Stima della qualità dell'aria

Il modello usa una formula trasparente:

```text
estimated_value =
    idw_base
    + traffic_factor * traffic_index
    - green_factor * green_index
    + weather_adjustment
```

### IDW

IDW significa **Inverse Distance Weighting**.

Idea: una stazione vicina pesa più di una stazione lontana.

Per ogni sensore virtuale:

1. si prendono le osservazioni ARPAC disponibili;
2. si calcola la distanza dal sensore virtuale;
3. si combinano i valori dando peso maggiore alle distanze minori.

### Traffic index

Il traffico è un proxy orario:

- alto nei giorni feriali 08:00-10:00 e 17:00-19:00;
- medio nei giorni feriali 11:00-16:00;
- basso di notte e nel weekend;
- maggiorato per terminal bus e parcheggio.

### Green index

Il verde riduce in modo semplificato PM e NO2. Nel MVP è assegnato manualmente per sensore:

- area verde: alto;
- biblioteca: medio;
- terminal bus e parcheggio: basso.

### Weather adjustment

Il meteo agisce in modo semplice:

- vento: tende a ridurre PM e NO2;
- pioggia: tende a ridurre PM10 e PM2.5;
- pomeriggio assolato: può aumentare leggermente O3.

I coefficienti sono in `config/settings.yaml`.

## Heatmap GIS

La heatmap della dashboard non arriva direttamente da ARPAC. Viene costruita interpolando i valori dei sensori virtuali su una griglia regolare.

Questo aiuta l'utente a vedere pattern spaziali, ma non deve essere interpretato come una misura continua reale.

## Scenari what-if

Gli scenari modificano i valori stimati in modo controllato:

- riduzione traffico: riduce la componente traffico;
- zona intervento: applica l'effetto soprattutto alla zona scelta;
- verde aggiunto: aumenta la riduzione associata al verde;
- vento: moltiplica la velocità del vento;
- pioggia: applica un evento pioggia semplificato.

La dashboard mostra:

- baseline;
- scenario;
- delta.

Il delta è il risultato più utile per leggere gli scenari, perché mostra la differenza tra prima e dopo.

Gli scenari possono essere applicati anche a finestre temporali:

- solo ora selezionata;
- mattina;
- pranzo;
- pomeriggio;
- giornata intera.

La dashboard aggrega il delta anche per zona funzionale, così l'utente può confrontare l'effetto spaziale dell'intervento.

## Affidabilità spaziale

Il layer di affidabilità è dimostrativo. Viene calcolato in base alla distanza dal sensore virtuale più vicino:

- alta vicino ai sensori;
- più bassa nelle aree lontane dai sensori.

Non rappresenta incertezza scientifica completa, ma aiuta l'utente a capire dove la simulazione è più o meno supportata dai punti disponibili.

## Validazione solo con dati open

Se non sono disponibili sensori fisici nel campus e non si possono usare dati chiusi, il controllo di qualità più difendibile è una validazione interna sui dati ARPAC open.

Il progetto usa una procedura **leave-one-station-out** sulle ore recenti disponibili:

1. per ogni ora e inquinante si selezionano le stazioni ARPAC con valore e coordinate;
2. una stazione viene esclusa temporaneamente;
3. il valore della stazione esclusa viene stimato usando le altre stazioni con IDW;
4. la stima viene confrontata con il valore osservato.

Il report `model_validation_summary.json` espone:

- MAE medio;
- bias medio;
- errore assoluto al percentile 90;
- metriche aggregate per inquinante.

Questa validazione non dimostra che il valore dentro il campus sia esatto, perché non esiste una misura campus reale da confrontare. Però misura quanto il metodo IDW riesce a ricostruire stazioni ARPAC note partendo da altre stazioni ARPAC, usando solo dati aperti.

Per mantenere il calcolo praticabile nella pipeline, la validazione usa per default le ultime ore disponibili configurate in `validation.max_hours`. I valori fuori da un intervallo fisicamente plausibile, per esempio flag numerici molto alti, vengono trattati come mancanti prima del modello e della validazione.

## Incertezza delle stime

Ogni stima campus include anche:

- numero di stazioni usate;
- distanza dalla stazione ARPAC più vicina;
- distanza media dalle stazioni;
- `uncertainty_score`;
- `confidence_label`.

L'incertezza aumenta quando le stazioni sono poche, lontane o quando il sistema deve usare fallback sintetici. È un indicatore operativo e trasparente, non un intervallo di confidenza regolatorio.

## Human-centered design

Le scelte di interfaccia seguono alcuni principi:

- spiegazioni vicino ai controlli, non solo nel README;
- preset narrativi invece di soli parametri tecnici;
- legenda sempre disponibile;
- progressiva disclosure: prima mappa e scenario, poi metodologia;
- avvisi chiari sui limiti;
- linguaggio operativo e non specialistico.

## Limiti

- Il modello è dimostrativo.
- I sensori sono virtuali.
- Le coordinate dei sensori sono sintetiche.
- La heatmap è interpolata.
- Il traffico è un proxy orario, non un dato misurato.
- Le relazioni meteo-inquinanti sono semplificate.
- Non è un modello sanitario, normativo o regolatorio.
- La validazione usa stazioni ARPAC, non sensori reali nel campus.
