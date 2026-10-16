# SEO Italia: CFO esterno e gestionali su misura

## Perimetro
- Revisione di `/servizi/controllo`, senza cambiare l'URL esistente.
- Nuove pagine `/servizi/cfo-esterno` e `/servizi/software-gestionali-su-misura`.
- Collegamenti descrittivi dalla home e dall'elenco servizi; rimando dalla digitalizzazione allo sviluppo.
- Nuovi slug nell'allowlist: la sitemap esistente li include automaticamente.
- Titoli e descrizioni distinti; canonical e Open Graph ereditati dal template comune.
- Rimossi dalla pagina controllo riferimenti a dieci milioni di scenari e garanzie non documentate.
- Nessuna modifica a credenziali, tag Search Console, database o strumenti interattivi.

## Verifiche eseguite
`python -m unittest discover -s tests -p test_service_seo.py -v`: 14 test superati.
I test estraggono le route effettive da `app.py` e renderizzano i template con Flask isolato; articoli e landing della sitemap sono simulati vuoti. Nessuna importazione dell'app completa, migrazione o connessione al database.

Controllo locale Chromium delle tre pagine a 390, 768 e 1440 pixel: 9 combinazioni senza overflow orizzontale; apertura FAQ verificata. Verifica visiva della pagina CFO mobile.

## Non verificato
- Avvio dell'app completa, integrazioni, CRM, invio contatti e database.
- Deploy Railway, risposta HTTP del sito aggiornato, indicizzazione e posizioni Google.
- Volumi keyword e difficoltà SEO: priorità qualitative, non una classifica misurata.

## Dopo l'approvazione e il merge
1. Verificare il deploy Railway e i tre URL, canonical, metadati e sitemap online.
2. Controllare la navigazione home → servizio → contatti e il laboratorio.
3. Ispezionare le nuove pagine in Search Console senza reinviare inutilmente la sitemap.
4. Misurare clic non-brand, impressioni e CTR per pagina/servizio; contatti qualificati con fonte tracciata. Usare confronti a 28 giorni quando disponibili.

Non vengono promessi miglioramenti di ranking o tempi di indicizzazione.
