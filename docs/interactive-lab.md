# Laboratorio interattivo della home

Tre strumenti inseriti tra i servizi e l'agente AI. Nessuna modifica a backend, database, dipendenze Python, tag di verifica Google o configurazioni Railway. I tre pannelli si aprono nella home; non sono state create pagine dedicate.

## Funzioni
- Simulatore annuale a volumi e costi invariati: confronto ricavi, margine di contribuzione, risultato operativo e crediti stimati. Il beneficio sui giorni d'incasso è distinto dall'utile e calcolato a ricavi iniziali costanti.
- Percorso prima/dopo: ordine inventato in cinque fasi, due modalità, navigazione e reset. Nessun movimento o documento reale.
- Otto domande obbligatorie: riepilogo delle pratiche dichiarate e spiegazioni per ogni area, senza punteggio diagnostico arbitrario.
- Stampa e salvataggio PDF tramite browser per simulatore e test, con esclusione del resto del sito e indicazione di input, ipotesi e limiti.

## Privacy e limiti
Il nuovo JavaScript non usa fetch, API, storage, cookie o servizi esterni. I valori restano nel DOM e si azzerano ricaricando. Restano invariati gli script preesistenti del sito: la dichiarazione di trattamento locale si riferisce esclusivamente a questi tre strumenti. Eventuali future registrazioni di sessione devono mascherare i campi. Nessun evento analytics aggiunto in questa versione.

## Verifiche eseguite
- `node --test tests/test_interactive_lab.cjs`: 9 test superati, inclusi sconto 100%, dati non validi, perdite operative e incassi più lenti.
- Chromium isolato: invio dei moduli, invalidazione dei risultati modificati, validazione delle otto risposte, reset, cinque fasi, cambio modalità, stampa isolata e generazione PDF.
- Larghezze 375, 768 e 1440 px senza overflow orizzontale nel laboratorio.
- Nessuna richiesta di rete degli strumenti e nessun errore JavaScript nell'anteprima isolata.
- Rendering Jinja della home ereditata: un H1 e tag di verifica Google conservato.

Il collaudo non importa `app.py` e non avvia database, email, webhook o integrazioni reali. Non è stata eseguita l'intera suite preesistente, che importa l'app operativa. Da verificare dopo approvazione: integrazione nel deployment di staging, Safari/Firefox e stampa sul dispositivo dell'utente. Nessuna pubblicazione di produzione eseguita.

## Collaudo manuale prima del rilascio
1. Aprire `/` e controllare la sezione dopo i servizi e prima del chatbot.
2. Aprire tutti i pannelli anche usando Tab e Invio.
3. Confermare: 500.000 ricavi, 250.000 variabili, 150.000 fissi e sconto 5% producono risultato iniziale 100.000 e scenario 75.000 euro.
4. Confermare che cambiare i dati nasconda il vecchio risultato e il pulsante stampa.
5. Percorrere tutte le fasi prima/dopo e ripartire con Ricomincia.
6. Compilare le otto risposte, stampare il riepilogo, cambiare una risposta e azzerare.
7. Provare stampa e Salva come PDF: nessun menu o altro contenuto del sito nel documento.

## Rilascio e ripristino
Attendere autorizzazione al merge. Dopo il merge sul ramo effettivamente distribuito, verificare il deployment e i tre strumenti sull'URL pubblico; non assumere che il merge equivalga a un deploy riuscito. Per ripristinare, revert del commit del laboratorio. Nessuna migrazione dati necessaria.
