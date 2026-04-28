# Guida utente

Questa guida spiega come usare la dashboard **UNISA Air Quality Digital Twin - MVP** senza conoscenze tecniche di GIS, modellistica ambientale o programmazione.

## A cosa serve

La dashboard aiuta a esplorare, in modo dimostrativo, come potrebbe variare la qualità dell'aria nel Campus di Fisciano dell'Università di Salerno.

Puoi usarla per:

- vedere una stima spaziale di PM10, PM2.5, NO2 e O3 sul campus;
- confrontare zone diverse del campus;
- simulare scenari semplici, come meno traffico, pioggia o vento più forte;
- capire come dati pubblici, sensori virtuali e mappe GIS possono comporre un primo Digital Twin urbano.

## Cosa non è

Non è una rete ufficiale di monitoraggio. Non sostituisce ARPAC. Non deve essere usata per decisioni sanitarie, legali o regolatorie.

I valori sono stime dimostrative. Servono soprattutto per confrontare scenari e ragionare sul comportamento del sistema.

## Avvio rapido

Installa le dipendenze:

```bash
python3 -m pip install -r requirements.txt
```

Esegui la pipeline dati:

```bash
python3 scripts/run_pipeline.py
```

Avvia la dashboard:

```bash
python3 -m streamlit run app/streamlit_app.py
```

## Come leggere la dashboard

### Barra laterale

La barra laterale contiene i controlli principali:

- **Inquinante**: scegli PM10, PM2.5, NO2 o O3.
- **Ora simulata**: scegli il momento da visualizzare.
- **Risoluzione griglia**: aumenta o riduce il dettaglio della heatmap. Valori più alti sono più dettagliati ma più lenti.
- **Layer GIS**: accendi o spegni edifici, strade, aree verdi, parcheggi, sensori virtuali e stazioni ARPAC.
- **Zone funzionali**: mostra aree sintetiche del campus come mobilità, parcheggi, didattica, verde e servizi.
- **Affidabilità spaziale**: mostra dove la stima è più vicina o più lontana dai sensori virtuali.

### GIS operativo

Questa vista mostra la situazione stimata sul campus.

Elementi principali:

- la heatmap rappresenta una superficie continua stimata;
- i punti dei sensori virtuali rappresentano luoghi significativi del campus;
- le stazioni ARPAC mostrano la rete ufficiale vicina, quando le coordinate sono disponibili;
- la tabella sotto la mappa riporta i valori per ogni sensore virtuale.

La heatmap non è una misura diretta: è ottenuta interpolando i valori dei sensori virtuali.

### Scenario builder

Questa sezione permette di costruire scenari GIS. Non scegli solo un valore globale: scegli anche **dove** e **quando** applicarlo.

Preset disponibili:

- **Personalizzato**: imposta manualmente tutti i controlli.
- **Ora di punta al terminal bus**: simula un intervento nella zona mobilità.
- **Parcheggio meno utilizzato**: simula meno pressione veicolare in zona parcheggio.
- **Giornata di pioggia**: applica una riduzione semplificata soprattutto su PM10 e PM2.5.
- **Vento forte**: aumenta l'effetto del vento.
- **Campus green mobility**: combina meno traffico e più verde.
- **Nuova area verde nei parcheggi**: simula una misura green nella zona parcheggio.

Puoi applicare lo scenario a:

- solo ora selezionata;
- mattina;
- pranzo;
- pomeriggio;
- giornata intera.

La mappa **Scenario** mostra il valore stimato dopo lo scenario.

La mappa **Delta per zona** mostra la differenza rispetto alla baseline:

- verde: miglioramento stimato;
- chiaro: variazione piccola;
- rosso: peggioramento stimato.

La sezione **Componenti del modello** mostra come base ARPAC, traffico, verde e meteo contribuiscono al valore finale di un sensore.

### Digital Twin

Questa sezione mostra gli asset del gemello digitale:

- zone funzionali;
- sensori virtuali;
- geometrie;
- schede entità;
- mappa di affidabilità spaziale.

Serve a leggere il campus come sistema di entità GIS, non solo come grafico ambientale.

### Serie temporali

Questa sezione mostra l'andamento nel tempo per un sensore virtuale. La linea verticale indica l'ora selezionata nella barra laterale.

### Guida e metodologia

Questa sezione spiega:

- cosa significa Digital Twin;
- da dove arrivano i dati;
- come funziona il modello;
- come interpretare gli scenari;
- quali sono i limiti.

### Qualità dati

Questa sezione mostra:

- numero di righe ARPAC caricate;
- numero di stazioni;
- ultimo aggiornamento;
- eventuale uso di dati sintetici fallback;
- distribuzione della confidenza delle stime;
- validazione open-data del modello contro stazioni ARPAC;
- avvisi di schema o provenienza.

La validazione open-data funziona così: il sistema nasconde temporaneamente una stazione ARPAC, prova a ricostruirne il valore dalle altre stazioni e misura l'errore. Non sostituisce sensori reali nel campus, ma rende il modello più controllabile usando solo dati aperti.

Se nei file ARPAC compaiono valori numerici anomali usati come flag di dato mancante, la pipeline li esclude prima di calcolare stime e validazione.

## Esempi guidati

### Esempio 1: ora di punta e NO2

1. Seleziona `NO2`.
2. Scegli un orario vicino alle 08:00 o 17:00.
3. Vai su **Scenario builder**.
4. Seleziona **Ora di punta al terminal bus**.
5. Imposta la finestra **Mattina**.
6. Guarda la mappa **Delta per zona**.

Se il modello produce un miglioramento, vedrai aree verdi nelle zone più influenzate dallo scenario.

### Esempio 2: effetto pioggia su PM10

1. Seleziona `PM10`.
2. Vai su **Scenario builder**.
3. Seleziona **Giornata di pioggia**.
4. Guarda il delta medio e la tabella sensori.

In questo MVP la pioggia riduce in modo semplificato le polveri.

### Esempio 3: confronto tra zone

1. Seleziona un inquinante.
2. Vai su **GIS operativo**.
3. Usa la tabella per ordinare i sensori dal valore più alto al più basso.
4. Confronta zone come mobilità, parcheggio, verde e studio.

## Glossario semplice

- **ARPAC**: agenzia regionale che gestisce dati ufficiali di qualità dell'aria.
- **OSM**: OpenStreetMap, mappa collaborativa usata per edifici, strade e aree verdi.
- **Sensore virtuale**: punto simulato sul campus, non uno strumento fisico.
- **Zona funzionale**: poligono sintetico che rappresenta una parte operativa del campus.
- **Heatmap**: superficie colorata che aiuta a vedere pattern spaziali.
- **IDW**: metodo semplice che stima un valore dando più peso ai punti vicini.
- **Baseline**: situazione stimata prima dello scenario.
- **Scenario**: situazione stimata dopo una modifica ipotetica.
- **Delta**: differenza tra scenario e baseline.
- **Affidabilità spaziale**: indicazione dimostrativa della vicinanza ai sensori virtuali.
