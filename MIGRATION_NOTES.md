# Migrazione Supabase → PostgreSQL Railway

## ✅ Status: 4 Agosto 2026

### Cosa è stato fatto:
1. **PostgreSQL 18 creato su Railway** con volume persistente automatico
2. **DATABASE_URL** aggiunto come variable di Railway che punta a PostgreSQL Railway
3. **Codice Python** è già configurato per usare `DATABASE_URL` e supporta sia SQLite che PostgreSQL

### Come attivare la migrazione:

**Passo 1:** Domani (4 agosto) il deploy sarà automatico. La connection a PostgreSQL Railway sarà usata.

**Passo 2:** Il database sarà inizialmente vuoto. Tabelle create automaticamente da SQLAlchemy.

**Passo 3:** (Opzionale) Se vuoi trasferire i dati vecchi da Supabase:
```bash
# Da Supabase
pg_dump -h db.dedvcoxqlocjdqkhxgwd.supabase.co -U postgres -d postgres > backup.sql

# A PostgreSQL Railway
psql -h $PGHOST -U $PGUSER -d $PGDATABASE < backup.sql
```

### Variabili ambiente pronte:
- `SMTP_SERVER` = smtps.aruba.it ✅
- `SMTP_PORT` = 465 ✅
- `SMTP_USER` = info@mauriziogustinicchiconsulting.it ✅
- `SMTP_PASSWORD` = [DA COMPILARE IN RAILWAY] ⚠️
- `DATABASE_URL` = ${{ Postgres.DATABASE_URL }} ✅

### Note importanti:
- **Supabase rimane attivo** finché non hai confermato tutto su Railway
- **Backup:** i dati vecchi restano su Supabase come backup
- **Admin panel:** tutto funziona uguale, legge da PostgreSQL Railway

---

## Variabili ambiente Railway richieste

Da impostare su Railway dashboard → web service → **Variables** (mai nel repository). Vedi anche `.env.example`.

### Sicurezza
- `SECRET_KEY` — stringa random di almeno 32 caratteri, usata da Flask per firmare sessioni/CSRF. Generarla con es. `python -c "import secrets; print(secrets.token_hex(32))"`.
- `ADMIN_USER` — nome utente admin del pannello (default `maurizio`).
- `ADMIN_PASSWORD` — password lunga e unica, diversa dal default di sviluppo (es. `MgcAdmin2026!Secure@123`).

### Database
- `DATABASE_URL` — connection string PostgreSQL Railway (già configurata, vedi sopra).

### Integrazione Google AI (generazione articoli con Gemini/Imagen)
- `GOOGLE_API_KEY` — chiave da Google AI Studio. Placeholder per ora, da sostituire con la chiave reale prima di usare l'assistente IA nel pannello admin.
- `ARTICLE_TEXT_MODEL` — modello Gemini per la generazione testo (default `gemini-2.5-flash`).
- `ARTICLE_IMAGE_MODEL` — modello Imagen per la generazione immagini (default `imagen-3.0-generate-002`).

### Metadati articoli
- `ARTICLE_AUTHOR` — nome autore predefinito per gli articoli (default `Maurizio Gustinicchi`, personalizzabile).

---
**Creato da Railway Agent il 3 agosto 2026**

