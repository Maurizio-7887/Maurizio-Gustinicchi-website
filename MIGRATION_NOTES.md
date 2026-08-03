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
**Creato da Railway Agent il 3 agosto 2026**

