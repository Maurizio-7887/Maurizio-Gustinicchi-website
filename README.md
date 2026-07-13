# MAURIZIO GUSTINICCHI CONSULTING — Sito Dinamico

Migrazione da statico (Aruba) a dinamico: Flask + PostgreSQL su Railway.

## Struttura

```
app.py                 # Applicazione Flask (route, blog, contatti, admin, SEO)
models.py              # Modelli DB: Articolo, Lead
seed_articoli.json     # I 6 articoli esistenti, importati automaticamente al primo avvio
templates/
  base.html            # Header/nav/footer unici per tutto il sito
  index.html, ...      # Pagine convertite dal sito Aruba (fedeli all'originale)
  blog_lista.html      # Lista blog DINAMICA (legge dal DB)
  blog_articolo.html   # Template articolo singolo (legge dal DB)
  servizi/*.html       # 8 pagine dettaglio servizi
  admin/*.html         # Pannello di gestione
static/                # css, img (ottimizzate: 79MB -> 8MB), video, docs (PDF certificati)
```

## Deploy su Railway

1. Crea un repo GitHub e pusha questa cartella.
2. Su Railway: **New Project → Deploy from GitHub repo**.
3. Aggiungi il plugin **PostgreSQL** (Railway imposta `DATABASE_URL` da solo).
4. Variabili d'ambiente da impostare sul servizio web:

| Variabile | Valore |
|---|---|
| `SECRET_KEY` | stringa casuale lunga |
| `ADMIN_USER` | il tuo username admin |
| `ADMIN_PASSWORD` | password robusta (default nel codice DA CAMBIARE) |
| `CRM_WEBHOOK_URL` | endpoint del CRM che riceve i lead (vedi sotto) |
| `CRM_API_KEY` | opzionale, inviata come header `X-API-Key` |
| `SITE_URL` | `https://www.mauriziogustinicchiconsulting.it` |

5. Al primo avvio il DB si crea da solo e i 6 articoli vengono importati (seed automatico).

## Dominio (resta su Aruba come registrar)

1. Railway → Settings → Domains → aggiungi `www.mauriziogustinicchiconsulting.it`.
2. Railway mostra un valore CNAME: inseriscilo nel pannello DNS di Aruba sul record `www`.
3. Per il dominio nudo (`mauriziogustinicchiconsulting.it`): su Aruba imposta il redirect
   verso `www.` (Aruba non supporta CNAME sul root; in alternativa usa i record A/ALIAS
   che Railway indica).
4. Attendi la propagazione DNS (da minuti a qualche ora). HTTPS automatico via Railway.

## Integrazione CRM (form contatti)

Ogni lead dal form `/contatti`:
1. Viene salvato nella tabella `leads` (backup locale, sempre).
2. Viene inviato in POST JSON a `CRM_WEBHOOK_URL` in un thread separato (il visitatore
   non aspetta la risposta del CRM).

Payload inviato al CRM:

```json
{
  "nome": "Mario Rossi",
  "email": "mario@azienda.it",
  "azienda": "ACME Srl",
  "telefono": "333 1234567",
  "messaggio": "Vorrei una consulenza...",
  "fonte": "Sito Web - mauriziogustinicchiconsulting.it",
  "data": "2026-07-12T15:30:00"
}
```

Nel CRM basta creare un endpoint che riceve questo JSON e crea il contatto/opportunità.
Se l'invio fallisce, il lead resta nel pannello admin con il pulsante **↻ Reinvia**.

## Pannello Admin

- URL: `/admin` (login su `/admin/login`)
- Gestione articoli blog: crea/modifica/elimina, bozze, data, copertina, HTML del corpo
- Vista lead ricevuti con stato sincronizzazione CRM e reinvio manuale

## SEO preservata

- Redirect **301** da tutti i vecchi URL `.html` ai nuovi (es. `/servizi.html` → `/servizi`,
  `/blog/articolo-X.html` → `/blog/X`)
- Meta description originali conservate su ogni pagina
- Schema.org FAQPage (JSON-LD) conservato sulla home
- `sitemap.xml` generata dinamicamente (include gli articoli pubblicati) e `robots.txt`
- Tag canonical su ogni pagina

## Correzioni applicate rispetto al sito Aruba

- Path Windows rotto in blog (`assets\img\copertina blog dicembre 2025 .jpg`) → rinominato
- Card duplicata in /servizi → la seconda ora è "Digitalizzazione & Lean"
- Icona errata `icona_analisi_montecarlo.png` → puntata al file reale
- Copertina CFO 3.0 mancante → usa la copertina dicembre 2025
- Anteprime JPG dei 3 certificati generate dai PDF
- File con spazi/apostrofi/parentesi rinominati in snake_case
- Immagini ottimizzate: 79 MB → 8 MB totali (icone da 4 MB → ~250 KB)
- Rimossi 5 video mp4 orfani mai referenzati (45 MB)
- Form contatti ora funzionante (prima aveva action="#")

## Sviluppo locale

```bash
pip install -r requirements.txt
python app.py   # SQLite locale, http://localhost:5000
```
