# Negozio unificato — 17 ottobre 2026

## Modifiche
- Unica voce NEGOZIO nel menu commerciale; LIBRI resta la pagina editoriale.
- `/negozio` riunisce manuali, altri prodotti attivi e le 12 schede MASTER Suite.
- `/shop` reindirizza con 301 a `/negozio#software`; escluso dalla lista della sitemap.
- Software: dicitura **A PREVENTIVO**, senza prezzi numerici nel catalogo pubblico.
- Titolo e copertina corretti per “La ragioneria del margine per addetti al marketing”. Slug e ID esistenti preservati per non spezzare link e checkout.
- Listino proposto: Ragioneria del margine 59 €, Executive Assistant 49 €, Distruzione Creatrice 79 €. Nessuno sconto fittizio, primato o esclusività aggiunta.

## Importante: codice e dati del catalogo sono separati
I prodotti già esistenti risiedono nel database. Cambiare il seed NON aggiorna quei record.
Non si risolve mostrando un prezzo diverso soltanto nel template: il checkout deve usare il medesimo prezzo registrato nel prodotto.

La pubblicazione di questo ramo, da sola, **non aggiorna titoli, copertine o prezzi dei prodotti già presenti**. È necessario il passaggio esplicito seguente, dopo approvazione del listino e backup del database.

## Applicazione del listino (solo previa autorizzazione)
Nel servizio/ambiente protetto che dispone di DATABASE_URL:

```sh
python scripts/aggiorna_catalogo_libri.py
# Controllare l'anteprima delle differenze.
python scripts/aggiorna_catalogo_libri.py --applica
```

Lo script non importa app.py, non avvia il sito, non esegue migrazioni, seed, invii CRM o pagamenti. Non richiede credenziali in chat o nei comandi. Aggiorna solo nome, descrizione, immagine e prezzo dei tre slug riconosciuti come libri; non crea prodotti mancanti e non riattiva prodotti inattivi. Esecuzioni successive senza differenze sono innocue. Prezzi modificati in futuro dall'amministratore restano tali: nessuna riscrittura automatica a ogni avvio.

Spedizione, ID e slug invariati. I totali e gli stati degli ordini registrati non vengono modificati. Poiché gli ordini attuali fanno riferimento al prodotto, possono mostrarne il nuovo nome; non è stata introdotta una nuova gestione dello storico. Per annullare l'aggiornamento usare i valori precedenti dell'anteprima o il backup, non un ripristino indiscriminato degli ordini.

## Collaudo
11 test isolati su SQLite in memoria: anteprima senza scritture, aggiornamento, idempotenza, prodotti mancanti/inattivi, conservazione totali ordini, rendering, vecchio percorso, titoli e prezzi checkout, totale di due copie con spedizione, mantenimento schede software e dicitura A PREVENTIVO.

Chromium locale a 390, 768 e 1440 px: immagini caricate, un solo H1, nessuna eccedenza orizzontale, collegamento alla sezione software funzionante. Dati sintetici, risorse esterne bloccate. Tracking esistente non eseguito nel collaudo. Pagamenti reali e PostgreSQL di produzione non collaudati.

## Controlli dopo pubblicazione e aggiornamento dati
1. `/negozio`: menu senza ACQUISTA, manuali e 12 software presenti.
2. `/shop`: reindirizzamento alla sezione software.
3. `/libri` e negozio: titolo/copertina del primo manuale coerenti.
4. GET checkout dei tre libri: prezzi 59 / 49 / 79 €, spedizione separata invariata.
5. Verificare spedizione, trattamento IVA e condizioni commerciali prima di promuovere il listino; nessuna aliquota è stata aggiunta o modificata.
6. Nessun acquisto reale durante il collaudo.
