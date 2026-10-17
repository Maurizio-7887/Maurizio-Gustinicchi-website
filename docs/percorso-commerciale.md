# Home e percorso commerciale — 17 ottobre 2026

## Intervento
- Home: beneficio iniziale, tre problemi/percorsi, invito al confronto gratuito, volto del professionista anticipato, metodo in quattro passaggi.
- Navigazione comune: Soluzioni, Come lavoro, Esperienze, Chi sono, Risorse e contatto principale. Area clienti separata. Formazione, libri, unico Negozio, blog, video, certificazioni e partner conservati nel menu Risorse, accessibile tramite elemento details nativo anche senza JavaScript.
- Tutti e tre gli strumenti preservati. Simulatore in evidenza; i collegamenti diretti aprono lo strumento corrispondente. Nessuna modifica a formule, prezzi o catalogo.
- FAQ pratiche e dati strutturati FAQ coerenti. Titolo SEO della home, descrizione, canonical, Person/ProfessionalService e verifica Search Console preservati.
- Video senza autoplay, con preload none, in un approfondimento facoltativo. Assistente AI in una sezione sempre visibile, con collegamento diretto dall'apertura della home. Assistente non rimosso né modificato nel funzionamento: messaggi più prudenti e avviso di non inserire informazioni personali o riservate.
- Contatti: nome, email e messaggio obbligatori; azienda e telefono facoltativi. Rimossa la scelta oggetto (non gestita dal backend esistente), telefono uniformato. Informativa distinta dall'eventuale consenso marketing, nessuna nuova iscrizione promozionale.
- Le tre pagine servizio indicano al modulo il percorso via parametro servizio, limitato a valori riconosciuti. Il parametro cambia solo il testo orientativo: non aggiunge campi al CRM né cambia attribuzione o invio. Il backend esistente conserva la pagina di provenienza secondo il comportamento già presente.
- Un'email professionale principale nel footer e nella pagina contatti. Mappa incorporata sostituita da collegamento esplicito: niente caricamento automatico dell'iframe Google su questa pagina.

## Verifiche
16 test unittest isolati superati, senza importare/avviare app.py. Inclusi: rendering, singolo H1, dati strutturati, corrispondenza FAQ, menu, strumenti, collegamento e indirizzo di richiesta dell'assistente AI preservati, parametri ammessi, campi obbligatori, token e honeypot, contatto sintetico valido, incompleto e spam. Per il test di invio viene compilata soltanto la funzione contatti del sorgente, con database, thread, email e CRM sostituiti: nessuna comunicazione o scrittura reale. La qualità e la disponibilità delle risposte AI del sito pubblico non sono state collaudate.

Chromium headless: home, contatti e tre servizi a 390, 768 e 1440 pixel (15 combinazioni), senza overflow orizzontale, con un solo H1 e immagini caricate; nessun errore JavaScript rilevato. Verificati menu Risorse, apertura del simulatore da collegamento, calcolo, percorso prima/dopo, autovalutazione e validazione HTML del modulo. Risorse esterne bloccate durante questo controllo: non è una misura delle prestazioni del sito pubblico.

Esecuzione test: `python -m unittest discover -s tests -p test_conversion_paths.py -v` (richiede Flask, già dipendenza applicativa).

## Limiti e controlli ancora necessari
- Nessun test di consegna email/CRM, database PostgreSQL, pagamenti, account pubblicitari o telefono fisico. Il codice backend di invio e protezione antispam è invariato.
- Nessun dato cliente, schermata di produzione, risultato economico o testimonianza aggiunto/inventato. Le testimonianze esistenti sono soltanto collegate, senza nuovi estratti; accuratezza e autorizzazioni devono essere verificate dal titolare.
- Privacy e cookie non riscritti: informativa attuale e trattamenti effettivi vanno verificati con un professionista prima delle campagne. Restano da analizzare font esterni, provenienza, chat AI, conservazione e fornitori.
- Nessun GA4, Meta Pixel, Google Ads, cookie banner o nuovo evento pubblicitario attivato. Gestione preferenze, eventi dopo invio effettivo e deduplicazione richiedono un incarico successivo con configurazione concordata.
- Velocità/Core Web Vitals e conversioni non misurati. Nessuna promessa di miglioramento del ranking o dei contatti.
- Nessun aggiornamento automatico del catalogo libri: resta separata la procedura esplicita della PR 7.
- Merge e pubblicazione richiedono autorizzazione. Questa modifica non introduce migrazioni o azioni operative all'avvio.
