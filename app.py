from flask import Flask, render_template, request, redirect, url_for, send_file, flash, jsonify, session 
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func, text
from sqlalchemy.schema import FetchedValue
from datetime import datetime, timedelta
import pandas as pd
import io
import os
import time
import calendar
# webview importato localmente nel blocco __main__ (non disponibile su Railway)
from threading import Thread
import requests
import webbrowser
import mailchimp_marketing as MailchimpMarketing
from mailchimp_marketing.api_client import ApiClientError
import google.genai as genai_new
from google.genai import types
import imaplib
import email
from email.header import decode_header
from datetime import datetime, timedelta, timezone
from functools import wraps
import tempfile
import base64
from werkzeug.utils import secure_filename
from content_factory import genera_video_reel, genera_piano_editoriale_ia, genera_campagna_ads, estrai_dati_preventivo_pdf
from geo_italia import REGIONI_ORDINATE, province_di_regione, regione_di_provincia


# ════════════════════════════════════════════════════════════════
# CONFIGURAZIONE — tutte le chiavi vengono lette dal file .env
# ════════════════════════════════════════════════════════════════
from dotenv import load_dotenv
load_dotenv()

ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY', '')
HUNTER_API_KEY    = os.environ.get('HUNTER_API_KEY', '')
MAILCHIMP_API_KEY = os.environ.get('MAILCHIMP_API_KEY', '')
MAILCHIMP_SERVER  = os.environ.get('MAILCHIMP_SERVER', 'us6')
MAILCHIMP_LIST_ID = os.environ.get('MAILCHIMP_LIST_ID', '')
GOOGLE_API_KEY    = os.environ.get('GOOGLE_API_KEY', '')

# Account email per la Mail Intelligence
ACCOUNT_EMAIL = [
    {
        'user': os.environ.get('EMAIL_1_USER', ''),
        'pass': os.environ.get('EMAIL_1_PASS', ''),
        'host': os.environ.get('EMAIL_1_HOST', 'imap.gmail.com'),
    },
    {
        'user': os.environ.get('EMAIL_2_USER', ''),
        'pass': os.environ.get('EMAIL_2_PASS', ''),
        'host': os.environ.get('EMAIL_2_HOST', 'imaps.aruba.it'),
    },
]

# Dati aziendali
AZIENDA_NOME  = os.environ.get('AZIENDA_NOME',  'Maurizio Gustinicchi Consulting')
AZIENDA_SITO  = os.environ.get('AZIENDA_SITO',  'www.mauriziogustinicchiconsulting.it')
AZIENDA_EMAIL = os.environ.get('AZIENDA_EMAIL', 'info@mauriziogustinicchiconsulting.it')
AZIENDA_FIRMA = os.environ.get('AZIENDA_FIRMA', 'Team Maurizio Gustinicchi Consulting | www.mauriziogustinicchiconsulting.it')

# ════════════════════════════════════════════════════════════════

mailchimp_client = MailchimpMarketing.Client()
mailchimp_client.set_config({
    "api_key": MAILCHIMP_API_KEY,
    "server":  MAILCHIMP_SERVER
})

MODELLO_ATTUALE = 'gemini-2.5-flash'
if GOOGLE_API_KEY:
    try:
        client_ai = genai_new.Client(api_key=GOOGLE_API_KEY)
    except Exception as e:
        print(f"⚠️  Gemini non inizializzato correttamente ({e}). Le funzioni IA risponderanno con un avviso.")
        client_ai = None
else:
    print("⚠️  GOOGLE_API_KEY non impostata: le funzioni IA (Email AI, Piano Editoriale, Ads) sono disattivate, il resto del CRM funziona normalmente.")
    client_ai = None


# ─────────────────────────────────────────────────────────────────
# FUNZIONI AI / EMAIL INTELLIGENCE
# ─────────────────────────────────────────────────────────────────

def chiedi_a_gemini(prompt):
    if client_ai is None:
        return {"sentiment": "Neutro", "urgenza": 5, "sintesi": "IA non configurata (manca GOOGLE_API_KEY)"}
    try:
        import json
        response = client_ai.models.generate_content(
            model=MODELLO_ATTUALE,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        return json.loads(response.text)
    except Exception:
        return {"sentiment": "Neutro", "urgenza": 5, "sintesi": "Errore analisi"}


def censimento_e_analisi_profonda(mail_connection):
    print("🚀 Avvio Analisi Profonda (Lettura Testo + IA)...")
    mail_connection.select("inbox")
    status, messages = mail_connection.search(None, 'ALL')
    mail_ids   = messages[0].split()
    ultimi_ids = mail_ids[-50:]
    ultimi_ids.reverse()

    for m_id in ultimi_ids:
        try:
            status, data = mail_connection.fetch(m_id, '(RFC822)')
            for response in data:
                if isinstance(response, tuple):
                    msg           = email.message_from_bytes(response[1])
                    subject_data  = decode_header(msg.get("Subject", "Nessun Oggetto"))[0]
                    subject       = subject_data[0]
                    if isinstance(subject, bytes):
                        subject = subject.decode(subject_data[1] or 'utf-8', errors='ignore')
                    sender = msg.get("From")
                    body   = ""
                    if msg.is_multipart():
                        for part in msg.walk():
                            if part.get_content_type() == "text/plain":
                                body = part.get_payload(decode=True).decode(errors='ignore')
                                break
                    else:
                        body = msg.get_payload(decode=True).decode(errors='ignore')
                    print(f"🔍 Analisi in corso: {subject[:40]}...")
                    analizza_e_salva_mail(sender, subject, body)
        except Exception as e:
            print(f"❌ Errore durante l'analisi della mail {m_id}: {e}")

    print("\n✅ Analisi completata!")


def classify_email(oggetto, testo, mittente):
    s = str(oggetto).lower()
    t = str(testo).lower()
    m = str(mittente).lower()
    testo_totale = f"{s} {t} {m}"

    parole_sempre_salva = [
        "reclamo", "diffida", "avvocato", "denuncia",
        "rimborso", "risoluzione contratto", "insoddisfatto",
        "conferma ordine", "ordine per", "nuovo ordine"
    ]
    is_sempre_salva = any(p in s for p in parole_sempre_salva)

    # TODO Maurizio Gustinicchi Consulting: inserire qui le email dei clienti/contatti VIP
    # da segnalare sempre (es. "mario.rossi@clienteimportante.it")
    vip_email_esatte = [
    ]
    is_vip_assoluto = any(v in m for v in vip_email_esatte)

    # TODO Maurizio Gustinicchi Consulting: inserire qui parole chiave/nomi di contatti VIP
    vip_per_nome = []
    is_vip_per_nome = any(v in m for v in vip_per_nome)

    if not is_vip_assoluto and not is_sempre_salva:
        domini_spam = [
            "jobalert", "indeed", "linkedin", "glassdoor", "jooble",
            "trovit", "mygigroup", "infojobs", "monster",
            "coursera", "emeritus", "iapp.org", "ulama", "academia-mail",
            "databricks", "lenovys", "kajabi", "kajabimail",
            "heygen", "learn.heygen",
            "edenred", "ticketrestaurant", "eventbrite", "salesforce",
            "odoo", "supabase", "zoom", "smartness", "pixlr", "experteer",
            "compass", "moto.it", "automoto", "lrqa", "aprilsolution",
            "chinooky", "beta imprese", "assopm",
            "deutsche bank", "intesa", "unicredit",
            "noreply", "no-reply", "donotreply", "newsletters-noreply",
            "yahoo.com", "google.com", "libero.it",
            "alessandrobentivoglio", "simonemilani", "mik cosentino",
            "chabe", "ninja", "makeup", "kiss kiss", "pratiche auto",
            "bdmformazione", "bdm-formazione"
        ]
        if any(d in m for d in domini_spam):
            return "RUMORE"

        pattern_spam_oggetto = [
            "annuncio di lavoro", "nuovi annunci", "sta assumendo",
            "offerta di lavoro", "posizione aperta", "candidatura per",
            "webinar", "workshop", "siamo live", "live:",
            "newsletter", "unsubscribe", "cancella iscrizione",
            "profitti trading", "investimento", "guadagna",
            "checklist gratuita", "scarica gratis", "ebook gratuito",
            "agente di calcio", "esperimento ads", "deploying ai",
            "untitled", "franchising", "certificazione iso",
            "buoni pasto", "ticket restaurant", "roadmap ai",
            "ultima chance", "time is ticking", "free access expires",
            "ramadan", "lifetime access", "vorrei collegarmi",
            "project management tramite", "element condiviso con te"
        ]
        if any(p in s for p in pattern_spam_oggetto):
            return "RUMORE"

        parole_business_reale = [
            "preventivo", "ordine", "fattura", "pagamento", "incarico",
            "contratto", "proposta",
            "urgente", "problema", "errore", "non funziona",
            "reclamo", "lamentela", "segnalazione",
            "corso", "formazione", "docente", "aula", "its",
            "erp", "sap", "crm", "gestionale",
            "appuntamento", "incontro", "riunione", "chiamata",
            "collaborazione", "progetto",
            "segnaletica", "cartellonistica"
        ]
        contiene_business = any(p in testo_totale for p in parole_business_reale)
        if not contiene_business and not is_vip_per_nome:
            return "RUMORE"

    corpo_pulito = testo.strip()[:1500] if testo else "Nessun contenuto"
    prompt = f"""
Sei l'assistente email di {AZIENDA_NOME}, azienda italiana di formazione e networking.

CONTESTO:
- I CLIENTI sono: aziende, enti di formazione, ITS, confcommercio
- {AZIENDA_NOME} VENDE servizi formativi e di community, non li compra
- NON interessano: offerte di lavoro, corsi per noi, webinar commerciali, promozioni

ANALIZZA QUESTA EMAIL:
MITTENTE: {mittente}
OGGETTO: {oggetto}
CONTENUTO:
{corpo_pulito}

CLASSIFICA:
- "Negativo" → reclamo reale, problema serio, cliente insoddisfatto
- "Positivo" → azienda/ente che vuole acquistare un servizio, ordine, collaborazione
- "Neutro"   → contatto reale con info utili ma non urgenti
- "SPAM"     → promozioni, newsletter, recruiting, webinar, esercizi, qualsiasi cosa NON sia un cliente che vuole comprare

Il riassunto deve dire COSA VUOLE il mittente in max 10-12 parole.

Rispondi SOLO in JSON:
{{"sentiment": "Positivo/Negativo/Neutro/SPAM", "riassunto": "cosa vuole concretamente"}}
"""
    try:
        import json
        response = client_ai.models.generate_content(
            model=MODELLO_ATTUALE,
            contents=prompt,
            config=types.GenerateContentConfig(response_mime_type="application/json")
        )
        risultato = json.loads(response.text)
        if risultato.get("sentiment") == "SPAM":
            if is_sempre_salva:
                risultato["sentiment"] = "Negativo"
                risultato["riassunto"] = f"⚠️ DA LEGGERE: {risultato.get('riassunto', '')}"
            else:
                return "RUMORE"
        if (is_vip_assoluto or is_vip_per_nome) and risultato["sentiment"] != "Negativo":
            risultato["sentiment"] = "Positivo"
            risultato["riassunto"] = f"⭐ VIP: {risultato['riassunto']}"
        return risultato
    except Exception as e:
        print(f"⚠️ Errore Gemini: {e}")
        if is_vip_assoluto or is_vip_per_nome:
            return {"sentiment": "Positivo", "riassunto": "⭐ VIP: Leggere manualmente"}
        if is_sempre_salva:
            return {"sentiment": "Negativo", "riassunto": "⚠️ Email critica - leggere subito"}
        return "RUMORE"


def analizza_e_salva_mail(mittente, oggetto, corpo):
    risultato = classify_email(oggetto, corpo, mittente)
    if risultato == "RUMORE":
        return
    esiste = EmailAlert.query.filter_by(
        mittente=mittente,
        oggetto=oggetto[:200]
    ).first()
    if esiste:
        return
    nuovo_alert = EmailAlert(
        mittente        = mittente,
        oggetto         = oggetto[:200],
        testo_breve     = corpo[:500] if corpo else "",
        sentiment       = risultato.get("sentiment", "Neutro"),
        urgenza         = 5,
        sintesi_ia      = risultato.get("riassunto", "")[:255],
        data_ricezione  = datetime.utcnow(),
        letta           = False
    )
    db.session.add(nuovo_alert)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Errore salvataggio mail '{oggetto[:40]}': {e}")


def sync_email_intelligence():
    with app.app_context():
        data_limite = (datetime.now() - timedelta(days=7)).strftime("%d-%b-%Y")
        for acc in ACCOUNT_EMAIL:
            try:
                print(f"📡 Connessione a {acc['user']}...")
                mail = imaplib.IMAP4_SSL(acc['host'], 993)
                mail.login(acc['user'], acc['pass'])
                mail.select("inbox")
                status, messages = mail.search(None, f'(SINCE {data_limite})')
                mail_ids         = messages[0].split()
                ids_da_analizzare = mail_ids[-50:]
                ids_da_analizzare.reverse()
                print(f"📂 Trovate {len(ids_da_analizzare)} email recenti...")
                for m_id in ids_da_analizzare:
                    res, msg_data = mail.fetch(m_id, "(RFC822)")
                    for response in msg_data:
                        if isinstance(response, tuple):
                            msg          = email.message_from_bytes(response[1])
                            subject_data = decode_header(msg.get("Subject", "Nessun Oggetto"))[0]
                            subject      = subject_data[0]
                            if isinstance(subject, bytes):
                                subject = subject.decode(subject_data[1] or 'utf-8', errors='ignore')
                            sender = msg.get("From")
                            body   = ""
                            if msg.is_multipart():
                                for part in msg.walk():
                                    if part.get_content_type() == "text/plain":
                                        body = part.get_payload(decode=True).decode(errors='ignore')
                                        break
                            else:
                                body = msg.get_payload(decode=True).decode(errors='ignore')
                            print(f"🤖 Analisi IA: {subject[:50]}...")
                            analizza_e_salva_mail(sender, subject, body)
                mail.logout()
                print(f"✅ Sincronizzazione {acc['user']} completata.")
            except Exception as e:
                print(f"❌ ERRORE CRITICO su {acc['user']}: {e}")


# ─────────────────────────────────────────────────────────────────
# APP FLASK
# ─────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'iron_segnaletica_crm_2026_v1')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://localhost/crm_db')
if DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = DATABASE_URL
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    'pool_pre_ping': True,
    'pool_recycle': 300,
    'connect_args': {'connect_timeout': 10},
}
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

from social_bridge import social_bp

# ── BRIDGE: registra i blueprint ──
app.register_blueprint(social_bp)

db_lock = {"busy": False, "user": None, "timestamp": 0}

# ─────────────────────────────────────────────────────────────────
# CREDENZIALI UTENTI
# ─────────────────────────────────────────────────────────────────
UTENTI = {
    # unico utente: accesso completo, nessuna gerarchia/team da gestire
    "maurizio": {"password": os.environ.get("MAURIZIO_PASSWORD", "CHANGE_ME_2026!"), "livello": "admin", "nome_display": "Maurizio Gustinicchi", "capo_area": None},
}

def subagenti_di(capo_username):
    """Lista degli username che riportano (capo_area) a capo_username."""
    return [u for u, info in UTENTI.items() if info.get('capo_area') == capo_username]

def team_di(username):
    """Il proprio username + eventuali subagenti (per capo_area); solo se stesso altrimenti."""
    return [username] + subagenti_di(username)

# ─────────────────────────────────────────────────────────────────
# DECORATORI AUTH
# ─────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'utente' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'utente' not in session:
            return redirect(url_for('login'))
        if session.get('livello') != 'admin':
            flash('⛔ Accesso negato.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def direzione_required(f):
    """Admin + Angelo ('generale' = fa tutto). Claudio e i subagenti NON entrano qui
    (restano fuori dai moduli marketing/direzionali, salvo diversa richiesta)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'utente' not in session:
            return redirect(url_for('login'))
        if session.get('livello') not in ['admin', 'generale']:
            flash('⛔ Accesso negato.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def capo_area_required(f):
    """Admin + Angelo + Claudio (capo_area). Usata per funzioni di assegnazione/condivisione."""
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'utente' not in session:
            return redirect(url_for('login'))
        if session.get('livello') not in ['admin', 'generale', 'capo_area']:
            flash('⛔ Accesso negato.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def puo_vedere_direzionali():
    return session.get('livello') in ['admin', 'generale']


def puo_assegnare_clienti():
    """Solo Angelo (livello 'generale') e l'admin possono assegnare un cliente a un subagente."""
    return session.get('livello') in ['admin', 'generale']


def puo_condividere_clienti():
    """Angelo e Claudio (capo_area) possono condividere un cliente con qualcun altro."""
    return session.get('livello') in ['admin', 'generale', 'capo_area']


def clienti_visibili_query(vista_username=None):
    """
    Ritorna una query SQLAlchemy su Cliente già filtrata in base a chi è
    loggato (session['livello'] / session['utente']), applicando anche le
    condivisioni puntuali (ClienteCondivisione) e, se fornito, il filtro
    opzionale scelto dal menu a tendina 'vista_username'.
    """
    livello  = session.get('livello')
    username = session.get('utente')

    if livello in ('admin', 'generale'):
        # Angelo/admin vedono tutto. Il menu a tendina permette di restringere
        # la vista a un agente/team specifico, ma è un filtro di comodo, non
        # una restrizione di sicurezza (loro possono vedere comunque tutto).
        if vista_username and vista_username != 'tutti':
            squadra = team_di(vista_username)
            return Cliente.query.filter(Cliente.agente_username.in_(squadra))
        return Cliente.query

    if livello == 'capo_area':
        squadra = team_di(username)  # se stesso + subagenti
        if vista_username and vista_username != 'tutti' and vista_username in squadra:
            squadra = team_di(vista_username)
        condivisi_ids = [c.cliente_id for c in
                         ClienteCondivisione.query.filter_by(username_condiviso=username).all()]
        return Cliente.query.filter(
            db.or_(Cliente.agente_username.in_(squadra), Cliente.id.in_(condivisi_ids))
        )

    # subagente: solo il/i cliente/i assegnato/i + eventuali condivisioni ricevute
    condivisi_ids = [c.cliente_id for c in
                     ClienteCondivisione.query.filter_by(username_condiviso=username).all()]
    return Cliente.query.filter(
        db.or_(Cliente.agente_username == username, Cliente.id.in_(condivisi_ids))
    )


def vista_agente_corrente():
    """Selettore intelligente 'Mostra clienti di...': vive SOLO nella Dashboard
    (unico punto di impostazione iniziale), ma il valore scelto viene
    ricordato in sessione e riusato automaticamente in tutte le altre
    schermate (Pipeline Preventivi, viste mobile, ecc.) così Angelo/Claudio
    lo impostano una volta sola e lo ritrovano ovunque, senza doverlo
    riselezionare pagina per pagina."""
    if 'vista' in request.args:
        session['vista_agente'] = request.args.get('vista', 'tutti')
    return session.get('vista_agente', 'tutti')


def opzioni_vista_menu():
    """Costruisce la lista di opzioni per il menu a tendina 'Mostra clienti di...',
    disponibile solo per chi ha un team sotto di sé (admin/generale/capo_area)."""
    livello  = session.get('livello')
    username = session.get('utente')
    if livello in ('admin', 'generale'):
        return [('tutti', 'Tutti i clienti')] + [
            (u, info['nome_display']) for u, info in UTENTI.items() if u != 'admin'
        ]
    if livello == 'capo_area':
        squadra = subagenti_di(username)
        opzioni = [('tutti', 'Tutti i miei + team'), (username, 'Solo i miei')]
        opzioni += [(u, UTENTI[u]['nome_display']) for u in squadra]
        return opzioni
    return []


# ─────────────────────────────────────────────────────────────────
# FILTRO PER REGIONE (zona geografica), oltre alla singola provincia.
# Usato su dashboard/lista rossa/pipeline preventivi/mobile: quando si è
# fuori sede in una zona (es. Milano/Lombardia) si può restringere la
# vista a tutti i clienti di quella regione, indipendentemente dalla
# provincia esatta.
# ─────────────────────────────────────────────────────────────────

def opzioni_regione_menu():
    """Lista di opzioni per il menu a tendina 'Filtra per regione'."""
    return [('', 'Tutte le regioni')] + [(r, r) for r in REGIONI_ORDINATE]


# ─────────────────────────────────────────────────────────────────
# PROMEMORIA "DA VISITARE" (visite fisiche in zona, decise da Angelo).
# Si interseca volutamente con la Lista Rossa (che invece scatta in
# automatico sulla base di frequenza_ricontatto / ultimo contatto): sono
# due segnali diversi sullo stesso cliente, quindi li incrociamo con dei
# badge invece di tenerli separati, e "Segna visita effettuata" resetta
# ENTRAMBI i timer (una visita in sede vale anche come contatto).
# ─────────────────────────────────────────────────────────────────

FREQUENZA_VISITA_GIORNI = {
    'Mensile':        30,
    'Bimestrale':     60,
    'Trimestrale':    90,
    'Quadrimestrale': 120,
    'Semestrale':     180,
    'Annuale':        365,
}


def opzioni_frequenza_visita():
    return [('', 'Nessuna (non pianificata)')] + [(k, k) for k in FREQUENZA_VISITA_GIORNI]


def clienti_da_visitare(query, oggi):
    """Ritorna lista di tuple (cliente, data_scadenza_visita) per i clienti a
    cui Angelo ha assegnato una frequenza di visita e che risultano scaduti,
    ordinati dal più scaduto. Non blacklistati."""
    risultato = []
    candidati = query.filter(
        Cliente.blacklisted == False,
        Cliente.frequenza_visita.isnot(None),
        Cliente.frequenza_visita != ''
    ).all()
    for c in candidati:
        giorni = FREQUENZA_VISITA_GIORNI.get(c.frequenza_visita)
        if not giorni:
            continue
        riferimento = c.data_ultima_visita or c.data_creazione or oggi
        scadenza    = riferimento + timedelta(days=giorni)
        if scadenza <= oggi:
            risultato.append((c, scadenza))
    risultato.sort(key=lambda t: t[1])
    return risultato


def filtra_query_per_regione(query, regione):
    """Applica alla query su Cliente (o Preventivo joinato con Cliente) il
    filtro sulle sigle provincia della regione scelta. Se la regione non è
    valorizzata o non riconosciuta, ritorna la query invariata."""
    if not regione:
        return query
    sigle = province_di_regione(regione)
    if not sigle:
        return query
    return query.filter(Cliente.provincia.in_(sigle))


def e_autenticato():
    return 'utente' in session


# ─────────────────────────────────────────────────────────────────
# MODELLI DATABASE
# ─────────────────────────────────────────────────────────────────

# NOTA: il piano editoriale è generato e gestito direttamente qui
# (tab "Piano Editoriale IA" in Marketing AI) — nessuna dipendenza
# esterna da Streamlit o da un secondo database: tutto vive in questo
# stesso Postgres.
class EditorialPlan(db.Model):
    __tablename__ = 'editorial_plan'
    id                   = db.Column(db.Integer, primary_key=True)
    data                 = db.Column(db.String(10), nullable=False)
    canale               = db.Column(db.String(50))
    tipo                 = db.Column(db.String(50))
    titolo               = db.Column(db.String(200))
    brief                = db.Column(db.Text)
    stato                = db.Column(db.String(50), default="⏳ Pianificato")
    ultimo_aggiornamento = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id, "Data": self.data, "Canale": self.canale,
            "Tipo": self.tipo, "Titolo": self.titolo,
            "Brief": self.brief, "Stato": self.stato
        }


class Cliente(db.Model):
    id                    = db.Column(db.Integer, primary_key=True)
    nome                  = db.Column(db.String(100), nullable=False)
    p_iva                 = db.Column(db.String(20), unique=True, nullable=True)
    tipo_anagrafica       = db.Column(db.String(20), default='Lead')
    blacklisted           = db.Column(db.Boolean, default=False)
    spunta_direzionale    = db.Column(db.Boolean, default=False)
    frequenza_ricontatto  = db.Column(db.Integer, default=60)
    data_prossimo_contatto= db.Column(db.DateTime, nullable=True)
    mail_aperta           = db.Column(db.Boolean, default=False)
    download_effettuato   = db.Column(db.Boolean, default=False)
    data_ultimo_contatto  = db.Column(db.DateTime, nullable=True)
    ultima_data_acquisto  = db.Column(db.DateTime, nullable=True)
    data_creazione        = db.Column(db.DateTime, default=datetime.utcnow)
    telefono              = db.Column(db.String(20))
    email                 = db.Column(db.String(100))
    provincia             = db.Column(db.String(2))
    referente_acquisti    = db.Column(db.String(100))
    # NOTA: username (chiave di UTENTI) dell'agente/subagente a cui il
    # cliente è assegnato. NULL = non ancora assegnato a nessuno.
    agente_username       = db.Column(db.String(50), nullable=True)
    # NOTA: promemoria "Da Visitare" — la frequenza la decide SOLO Angelo
    # (vedi puo_vedere_direzionali), separata dalla frequenza_ricontatto
    # automatica: serve per pianificare le visite fisiche in zona.
    frequenza_visita      = db.Column(db.String(20), nullable=True)   # es. 'Trimestrale'
    data_ultima_visita    = db.Column(db.DateTime, nullable=True)
    preventivi            = db.relationship('Preventivo', backref='cliente', lazy=True)
    tasks                 = db.relationship('Task', backref='cliente', lazy=True)
    note                  = db.relationship('NotaColorata', backref='cliente', lazy=True)


class ClienteCondivisione(db.Model):
    """Un cliente può essere condiviso in visione con un utente che non
    è il suo agente assegnato (es. Angelo o Claudio condividono un cliente
    con un altro subagente pur restando l'agente titolare invariato)."""
    __tablename__ = 'cliente_condivisione'
    id                  = db.Column(db.Integer, primary_key=True)
    cliente_id          = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    username_condiviso  = db.Column(db.String(50), nullable=False)
    creato_da           = db.Column(db.String(50))
    data_creazione      = db.Column(db.DateTime, default=datetime.utcnow)
    cliente             = db.relationship('Cliente', backref='condivisioni')





class Preventivo(db.Model):
    id                        = db.Column(db.Integer, primary_key=True)
    cliente_id                = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    descrizione               = db.Column(db.String(200))
    note_revisione            = db.Column(db.Text, nullable=True)
    numero_ordine             = db.Column(db.String(50), nullable=True)
    numero_preventivo         = db.Column(db.String(50), nullable=True)
    data_creazione            = db.Column(db.DateTime, default=datetime.utcnow)
    stato                     = db.Column(db.String(50), default='Preventivo')
    data_scadenza             = db.Column(db.DateTime, nullable=True)
    data_ultimo_aggiornamento = db.Column(db.DateTime, server_default=text('NOW()'), server_onupdate=FetchedValue())
    # NOTA: copia digitale del PDF realmente inviato al cliente, archiviata
    # automaticamente al momento del caricamento (nessuna doppia scrittura manuale)
    file_pdf                  = db.Column(db.LargeBinary, nullable=True)
    file_nome                 = db.Column(db.String(255), nullable=True)
    importo                   = db.Column(db.Numeric(10, 2), nullable=True)


class NotaColorata(db.Model):
    id              = db.Column(db.Integer, primary_key=True)
    cliente_id      = db.Column(db.Integer, db.ForeignKey('cliente.id'), nullable=False)
    testo           = db.Column(db.Text, nullable=False)
    tipo_contatto   = db.Column(db.String(50))
    colore          = db.Column(db.String(10))
    data_inserimento= db.Column(db.DateTime, default=datetime.utcnow)


class EmailAlert(db.Model):
    id             = db.Column(db.Integer, primary_key=True)
    mittente       = db.Column(db.String(120))
    oggetto        = db.Column(db.String(200))
    testo_breve    = db.Column(db.Text)
    sentiment      = db.Column(db.String(20))
    urgenza        = db.Column(db.Integer)
    sintesi_ia     = db.Column(db.String(255))
    data_ricezione = db.Column(db.DateTime, default=datetime.utcnow)
    letta          = db.Column(db.Boolean, default=False)


class Task(db.Model):
    id           = db.Column(db.Integer, primary_key=True)
    cliente_id   = db.Column(db.Integer, db.ForeignKey('cliente.id'))
    descrizione  = db.Column(db.String(255), nullable=False)
    data_scadenza= db.Column(db.DateTime)
    completato   = db.Column(db.Boolean, default=False)


# ─────────────────────────────────────────────────────────────────
# MODELLI AGENDA VISITE — Piano Marketing Commerciale
# ─────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────
# CONTEXT PROCESSOR
# ─────────────────────────────────────────────────────────────────

@app.context_processor
def inject_global_data():
    return {
        'datetime':              datetime,
        'db_lock':               db_lock,
        'Cliente':               Cliente,
        'sessione_livello':      session.get('livello'),
        'sessione_nome':         session.get('nome_display'),
        'puo_vedere_direzionali': puo_vedere_direzionali(),
        'azienda_nome':          AZIENDA_NOME,
        'azienda_sito':          AZIENDA_SITO,
    }


# ─────────────────────────────────────────────────────────────────
# AUTH ROUTES
# ─────────────────────────────────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'utente' in session:
        return redirect(url_for('dashboard'))
    error = None
    if request.method == 'POST':
        password = request.form.get('password', '').strip()
        utente   = UTENTI.get('maurizio')
        if not utente:
            error = "Utente non configurato."
        elif utente['password'] != password:
            error = "Password errata."
        else:
            session['utente']       = 'maurizio'
            session['livello']      = utente['livello']
            session['nome_display'] = utente['nome_display']
            session.permanent       = True
            flash(f"Benvenuto, {utente['nome_display']}!", 'success')
            return redirect(url_for('dashboard'))
    return render_template('login.html', error=error)


@app.route('/logout')
def logout():
    nome = session.get('nome_display', 'Utente')
    session.clear()
    flash(f"Arrivederci, {nome}. Sessione terminata.", 'info')
    return redirect(url_for('login'))


# ─────────────────────────────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────────────────────────────

@app.route('/')
@login_required
def dashboard():
    oggi     = datetime.utcnow()
    oggi_str = oggi.strftime('%Y-%m-%d')

    vista_username = vista_agente_corrente()
    regione_filtro = request.args.get('regione', '').strip()

    # Contatore ritardi piano editoriale (modello condiviso con Content Factory)
    ritardi_ped = EditorialPlan.query.filter(
        EditorialPlan.data < oggi_str,
        EditorialPlan.stato != "✅ Pubblicato"
    ).count()

    base_query = filtra_query_per_regione(clienti_visibili_query(vista_username), regione_filtro)

    tutti_i_non_blacklistati = base_query.filter(Cliente.blacklisted == False).all()
    clienti_critici = []
    for c in tutti_i_non_blacklistati:
        if c.data_prossimo_contatto:
            if c.data_prossimo_contatto <= oggi:
                clienti_critici.append(c)
        else:
            soglia_giorni = c.frequenza_ricontatto if c.frequenza_ricontatto else 60
            limite        = oggi - timedelta(days=soglia_giorni)
            u_acquisto    = c.ultima_data_acquisto or datetime.min
            u_contatto    = c.data_ultimo_contatto or datetime.min
            if u_acquisto <= limite and u_contatto <= limite:
                clienti_critici.append(c)

    clienti_critici.sort(key=lambda x: x.nome)

    # Promemoria "Da Visitare" (frequenza decisa da Angelo in scheda cliente)
    da_visitare_lista = clienti_da_visitare(
        filtra_query_per_regione(clienti_visibili_query(vista_username), regione_filtro), oggi
    )
    ids_critici     = {c.id for c in clienti_critici}
    ids_da_visitare = {c.id for c, _ in da_visitare_lista}

    tasks_manuali = Task.query.filter_by(completato=False).order_by(Task.data_scadenza.asc()).all()
    blacklistati  = filtra_query_per_regione(clienti_visibili_query(vista_username), regione_filtro)\
                        .filter(Cliente.blacklisted == True).all()
    pipeline = {
        f: filtra_query_per_regione(clienti_visibili_query(vista_username), regione_filtro)
              .filter_by(tipo_anagrafica=f, blacklisted=False).order_by(Cliente.nome.asc()).all()
        for f in ['Lead', 'Prospect', 'Cliente']
    }

    return render_template('dashboard.html',
        tasks            = tasks_manuali,
        clienti_critici  = clienti_critici,
        pipeline         = pipeline,
        blacklistati     = blacklistati,
        ritardi_ped      = ritardi_ped,
        opzioni_vista    = opzioni_vista_menu(),
        vista_corrente   = vista_username,
        opzioni_regione  = opzioni_regione_menu(),
        regione_corrente = regione_filtro,
        da_visitare      = da_visitare_lista,
        ids_critici      = ids_critici,
        ids_da_visitare  = ids_da_visitare,
        oggi_iso         = datetime.utcnow().strftime('%Y-%m-%d'),
    )


# ─────────────────────────────────────────────────────────────────
# CLIENTI
# ─────────────────────────────────────────────────────────────────

@app.route('/nuovo_cliente', methods=['GET', 'POST'])
@login_required
def nuovo_cliente():
    if request.method == 'POST':
        p_iva     = request.form.get('p_iva', '').strip() or None
        prov_input= request.form.get('provincia', 'PG').strip().upper()
        if not prov_input:
            prov_input = 'PG'
        nuovo = Cliente(
            nome               = request.form.get('nome', '').strip().upper(),
            p_iva              = p_iva,
            telefono           = request.form.get('telefono', '').strip(),
            email              = request.form.get('email', '').strip(),
            provincia          = prov_input[:2],
            referente_acquisti = request.form.get('referente_acquisti', '').strip(),
            spunta_direzionale = True if request.form.get('spunta_direzionale') else False,
            tipo_anagrafica    = 'Lead'
        )
        try:
            db.session.add(nuovo)
            db.session.commit()
        except Exception as e:
            print(f"Errore database: {e}")
            db.session.rollback()
        return redirect(url_for('dashboard'))
    return render_template('nuovo_cliente.html')


@app.route('/aggiorna_anagrafica_cliente/<int:cliente_id>', methods=['POST'])
@login_required
def aggiorna_anagrafica_cliente(cliente_id):
    c = Cliente.query.get_or_404(cliente_id)
    c.nome               = request.form.get('nome')
    c.email              = request.form.get('email')
    c.telefono           = request.form.get('telefono')
    c.p_iva              = request.form.get('p_iva')
    c.provincia          = request.form.get('provincia', '').upper()[:2]
    c.referente_acquisti = request.form.get('referente_acquisti')
    try:
        db.session.commit()
        flash(f"✅ Anagrafica di {c.nome} aggiornata!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Errore: {str(e)}", "danger")
    return redirect(url_for('dettaglio_cliente', cliente_id=c.id))


@app.route('/blacklist_cliente/<int:cliente_id>', methods=['POST'])
@login_required
def blacklist_cliente(cliente_id):
    c = Cliente.query.get_or_404(cliente_id)
    c.blacklisted = True
    db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/ripristina_cliente/<int:cliente_id>', methods=['POST'])
@login_required
def ripristina_cliente(cliente_id):
    c = Cliente.query.get_or_404(cliente_id)
    c.blacklisted = False
    db.session.commit()
    flash(f"✅ {c.nome} ripristinato!", "success")
    return redirect(url_for('dashboard'))


@app.route('/cliente/<int:cliente_id>')
@login_required
def dettaglio_cliente(cliente_id):
    c = Cliente.query.get_or_404(cliente_id)
    subagenti_disponibili = [
        (u, info['nome_display']) for u, info in UTENTI.items() if u != 'admin'
    ]
    condivisioni_attive = ClienteCondivisione.query.filter_by(cliente_id=cliente_id).all()
    # Toggle Direzionale bloccato solo se assegnato a Claudio/subagente (non ad Angelo/admin)
    livello_agente = UTENTI.get(c.agente_username, {}).get('livello') if c.agente_username else None
    toggle_direzionale_bloccato = (not c.spunta_direzionale and livello_agente
                                   and livello_agente not in ('generale', 'admin'))
    return render_template('dettaglio_cliente.html',
        cliente=c,
        interazioni=c.note,
        puo_assegnare=puo_assegnare_clienti(),
        puo_condividere=puo_condividere_clienti(),
        subagenti_disponibili=subagenti_disponibili,
        condivisioni_attive=condivisioni_attive,
        toggle_direzionale_bloccato=toggle_direzionale_bloccato,
        nome_agente_display=UTENTI.get(c.agente_username, {}).get('nome_display') if c.agente_username else None,
        puo_vedere_direzionali=puo_vedere_direzionali(),
        opzioni_frequenza_visita=opzioni_frequenza_visita(),
    )


@app.route('/cliente/<int:cliente_id>/assegna', methods=['POST'])
@login_required
def assegna_cliente(cliente_id):
    """Solo Angelo (livello 'generale') e l'admin possono assegnare un cliente
    a un subagente/capo area — regola esplicita richiesta."""
    if not puo_assegnare_clienti():
        flash('⛔ Solo Angelo può assegnare i clienti ai subagenti.', 'danger')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))

    c = Cliente.query.get_or_404(cliente_id)
    nuovo_agente = request.form.get('agente_username', '').strip()
    if nuovo_agente and nuovo_agente not in UTENTI:
        flash('⛔ Utente destinatario non valido.', 'danger')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))

    c.agente_username = nuovo_agente or None

    # REGOLA DIREZIONALE (simmetrica): la spunta segue SEMPRE l'agente.
    # - assegnato ad Angelo o admin (livello 'generale'/'admin') → direzionale ON
    #   (anche se era stata tolta per errore: riassegnando Angelo torna DIREZIONALE)
    # - assegnato a Claudio o a un subagente → direzionale OFF
    # - assegnato a nessuno → la spunta resta com'è (non tocchiamo nulla)
    disattivata_direzionale = False
    riattivata_direzionale  = False
    if c.agente_username:
        livello_nuovo = UTENTI[c.agente_username]['livello']
        if livello_nuovo in ('generale', 'admin'):
            if not c.spunta_direzionale:
                c.spunta_direzionale = True
                riattivata_direzionale = True
        else:
            if c.spunta_direzionale:
                c.spunta_direzionale = False
                disattivata_direzionale = True

    db.session.commit()
    nome = UTENTI.get(nuovo_agente, {}).get('nome_display', 'nessuno') if nuovo_agente else 'nessuno'
    msg = f"✅ Cliente assegnato a: {nome}"
    if disattivata_direzionale:
        msg += " — spunta DIREZIONALE disattivata automaticamente."
    if riattivata_direzionale:
        msg += " — spunta DIREZIONALE riattivata automaticamente."
    flash(msg, "success")
    return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))


@app.route('/cliente/<int:cliente_id>/condividi', methods=['POST'])
@login_required
def condividi_cliente(cliente_id):
    """Angelo e Claudio (capo_area) possono condividere la visione di un
    cliente con un altro utente, senza cambiarne l'agente titolare."""
    if not puo_condividere_clienti():
        flash('⛔ Non hai i permessi per condividere clienti.', 'danger')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))

    Cliente.query.get_or_404(cliente_id)  # 404 se il cliente non esiste
    destinatario = request.form.get('username_condiviso', '').strip()
    if destinatario not in UTENTI:
        flash('⛔ Utente destinatario non valido.', 'danger')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))

    esiste = ClienteCondivisione.query.filter_by(
        cliente_id=cliente_id, username_condiviso=destinatario
    ).first()
    if not esiste:
        db.session.add(ClienteCondivisione(
            cliente_id=cliente_id,
            username_condiviso=destinatario,
            creato_da=session.get('utente')
        ))
        db.session.commit()
        flash(f"✅ Cliente condiviso con {UTENTI[destinatario]['nome_display']}.", "success")
    else:
        flash("ℹ️ Era già condiviso con questo utente.", "info")
    return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))


@app.route('/cliente/<int:cliente_id>/rimuovi_condivisione/<int:condivisione_id>', methods=['POST'])
@login_required
def rimuovi_condivisione_cliente(cliente_id, condivisione_id):
    if not puo_condividere_clienti():
        flash('⛔ Non hai i permessi per gestire le condivisioni.', 'danger')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))
    cond = ClienteCondivisione.query.get_or_404(condivisione_id)
    db.session.delete(cond)
    db.session.commit()
    flash("Condivisione rimossa.", "success")
    return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))


@app.route('/cambia_natura_cliente/<int:cliente_id>', methods=['POST'])
@login_required
def cambia_natura_cliente(cliente_id):
    cliente = Cliente.query.get_or_404(cliente_id)
    # Un cliente assegnato a Claudio o a un subagente non può essere marcato
    # Direzionale: va prima rimossa l'assegnazione (o riassegnato ad Angelo).
    # Se invece è assegnato ad Angelo/admin, il toggle resta libero (coerente
    # con la regola: direzionale = gestione diretta di Angelo/admin).
    livello_agente = UTENTI.get(cliente.agente_username, {}).get('livello') if cliente.agente_username else None
    if (not cliente.spunta_direzionale and livello_agente
            and livello_agente not in ('generale', 'admin')):
        flash("⛔ Cliente assegnato a un agente: rimuovi prima l'assegnazione (o riassegnalo ad Angelo) per poterlo rendere Direzionale.", "danger")
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente.id))
    cliente.spunta_direzionale = not cliente.spunta_direzionale
    db.session.commit()
    flash("Natura cliente aggiornata!", "success")
    return redirect(url_for('dettaglio_cliente', cliente_id=cliente.id))


@app.route('/aggiorna_frequenza/<int:cliente_id>', methods=['POST'])
@login_required
def aggiorna_frequenza(cliente_id):
    c = Cliente.query.get_or_404(cliente_id)
    nuova_soglia = request.form.get('frequenza')
    if nuova_soglia:
        c.frequenza_ricontatto = int(nuova_soglia)
        db.session.commit()
        flash(f"Soglia ricontatto aggiornata a {nuova_soglia} giorni!", "success")
    return redirect(url_for('dettaglio_cliente', cliente_id=c.id))


@app.route('/imposta_frequenza_visita/<int:cliente_id>', methods=['POST'])
@direzione_required
def imposta_frequenza_visita(cliente_id):
    """Solo Angelo/admin decide se e ogni quanto un cliente va visitato di
    persona: alimenta il promemoria 'Da Visitare' in Dashboard."""
    c = Cliente.query.get_or_404(cliente_id)
    nuova_frequenza = (request.form.get('frequenza_visita') or '').strip()
    c.frequenza_visita = nuova_frequenza or None
    db.session.commit()
    if nuova_frequenza:
        flash(f"📅 Frequenza visita impostata: {nuova_frequenza}", "success")
    else:
        flash("📅 Promemoria visita disattivato per questo cliente.", "info")
    return redirect(url_for('dettaglio_cliente', cliente_id=c.id))


@app.route('/segna_visita/<int:cliente_id>', methods=['POST'])
@login_required
def segna_visita(cliente_id):
    """Chiunque visiti il cliente registra la visita: resetta sia il
    promemoria 'Da Visitare' sia (visto che una visita in sede vale come
    contatto) l'eventuale criticità in Lista Rossa."""
    c = Cliente.query.get_or_404(cliente_id)
    oggi = datetime.utcnow()
    c.data_ultima_visita        = oggi
    c.data_ultimo_contatto      = oggi
    c.data_prossimo_contatto    = None  # ricalcolata da frequenza_ricontatto
    db.session.commit()
    flash("✅ Visita registrata! Promemoria e Lista Rossa aggiornati.", "success")
    return redirect(url_for('dettaglio_cliente', cliente_id=c.id))


@app.route('/aggiorna_scadenza_cliente/<int:cliente_id>', methods=['POST'])
@login_required
def aggiorna_scadenza_cliente(cliente_id):
    intervallo_mesi = request.form.get('intervallo_mesi')
    if intervallo_mesi:
        cliente        = Cliente.query.get_or_404(cliente_id)
        mesi           = int(intervallo_mesi)
        nuova_scadenza = datetime.now() + timedelta(days=mesi * 30)
        cliente.data_prossimo_contatto = nuova_scadenza
        db.session.commit()
    return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))


# ─────────────────────────────────────────────────────────────────
# INTERAZIONI / NOTE
# ─────────────────────────────────────────────────────────────────

@app.route('/nuova_interazione/<int:cliente_id>', methods=['POST'])
@login_required
def nuova_interazione(cliente_id):
    c               = Cliente.query.get_or_404(cliente_id)
    tipo            = request.form.get('tipo_contatto')
    testo           = request.form.get('note')
    data_task       = request.form.get('data_scadenza_task')
    descrizione_task= request.form.get('descrizione_task_libera')
    data_evento_str = request.form.get('data_evento')

    if tipo == 'Pianificazione' or data_task:
        nuovo_task = Task(
            cliente_id   = cliente_id,
            descrizione  = descrizione_task or f"Contattare: {testo[:30] if testo else 'N.D.'}",
            data_scadenza= datetime.strptime(data_task, '%Y-%m-%d')
        )
        db.session.add(nuovo_task)
        if c.tipo_anagrafica == 'Lead':
            c.tipo_anagrafica = 'Prospect'
    else:
        data_finale = datetime.strptime(data_evento_str, '%Y-%m-%d') if data_evento_str else datetime.utcnow()
        nuova_nota  = NotaColorata(
            cliente_id     = cliente_id,
            testo          = testo,
            tipo_contatto  = tipo,
            colore         = 'Blu',
            data_inserimento= data_finale
        )
        c.data_ultimo_contatto = data_finale
        db.session.add(nuova_nota)

    db.session.commit()
    return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))


@app.route('/bulk_registra_evento', methods=['POST'])
@login_required
def bulk_registra_evento():
    """Registra lo stesso evento (es. 'ho mandato la mail X oggi a tutti i
    lead') su più clienti in una volta sola, invece di aprire ogni scheda
    cliente uno per uno."""
    tipo_contatto  = request.form.get('tipo_contatto', 'Email')
    testo          = (request.form.get('testo') or '').strip()
    data_evento_str= request.form.get('data_evento')
    target         = request.form.get('target', 'lead')

    if not testo:
        flash("❌ Scrivi una descrizione dell'evento prima di registrare.")
        return redirect(url_for('dashboard'))

    data_finale = datetime.strptime(data_evento_str, '%Y-%m-%d') if data_evento_str else datetime.utcnow()

    query = Cliente.query
    if target == 'lead':
        query = query.filter_by(tipo_anagrafica='Lead')
    elif target == 'prospect':
        query = query.filter_by(tipo_anagrafica='Prospect')
    elif target == 'lead_prospect':
        query = query.filter(Cliente.tipo_anagrafica.in_(['Lead', 'Prospect']))
    # target == 'tutti' → nessun filtro, prende tutta l'anagrafica

    clienti = query.all()
    for c in clienti:
        db.session.add(NotaColorata(
            cliente_id      = c.id,
            testo           = testo,
            tipo_contatto   = tipo_contatto,
            colore          = 'Blu',
            data_inserimento= data_finale
        ))
        c.data_ultimo_contatto = data_finale

    db.session.commit()
    flash(f"✅ Evento registrato su {len(clienti)} clienti.")
    return redirect(url_for('dashboard'))


@app.route('/elimina_interazione/<int:id>', methods=['POST'])
@login_required
def elimina_interazione(id):
    pin = request.form.get('pin_segreto')
    if pin == '1234':
        nota       = NotaColorata.query.get_or_404(id)
        cliente_id = nota.cliente_id
        db.session.delete(nota)
        db.session.commit()
        flash('Registrazione eliminata.', 'success')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))
    flash('PIN errato!', 'danger')
    return redirect(request.referrer)


@app.route('/modifica_interazione/<int:id>', methods=['POST'])
@login_required
def modifica_interazione(id):
    pin         = request.form.get('pin_segreto')
    nuovo_testo = request.form.get('nuovo_testo_nota')
    if pin == '1234':
        nota       = NotaColorata.query.get_or_404(id)
        cliente_id = nota.cliente_id
        if nuovo_testo:
            nota.testo = nuovo_testo
            db.session.commit()
            flash('Attività aggiornata!', 'success')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))
    flash('PIN errato!', 'danger')
    return redirect(request.referrer)


# ─────────────────────────────────────────────────────────────────
# PREVENTIVI
# ─────────────────────────────────────────────────────────────────

@app.route('/carica_preventivo_pdf_dashboard', methods=['POST'])
@login_required
def carica_preventivo_pdf_dashboard():
    """
    Come 'carica_preventivo_pdf', ma pensato per un pulsante unico in dashboard
    che serve tutti gli utenti: qui NON si parte dalla scheda del cliente, quindi
    il cliente giusto viene riconosciuto in automatico dalla P.IVA letta nel PDF.
    """
    f = request.files.get('file_preventivo')
    if not f or not f.filename:
        flash('⚠️ Nessun file selezionato.', 'warning')
        return redirect(url_for('dashboard'))

    if not f.filename.lower().endswith('.pdf'):
        flash('⚠️ Carica un file PDF (è lo stesso file che mandi al cliente).', 'warning')
        return redirect(url_for('dashboard'))

    oggetto_manuale = (request.form.get('oggetto') or '').strip()

    pdf_bytes = f.read()
    try:
        dati = estrai_dati_preventivo_pdf(pdf_bytes)
    except Exception as e:
        flash(f'❌ Errore durante la lettura del PDF: {e}', 'danger')
        return redirect(url_for('dashboard'))

    cliente = None
    if dati.get('piva_cliente'):
        cliente = Cliente.query.filter_by(p_iva=dati['piva_cliente']).first()

    if not cliente:
        flash("⚠️ Non sono riuscito a riconoscere automaticamente il cliente dalla P.IVA nel PDF "
              "(o il cliente non è ancora in anagrafica). Apri la scheda cliente corretta e carica "
              "il PDF da lì, oppure crea prima l'anagrafica.", "warning")
        return redirect(url_for('dashboard'))

    nuovo = Preventivo(
        cliente_id        = cliente.id,
        # L'oggetto scritto a mano da chi carica il preventivo ha sempre la
        # priorità (riassume meglio la trattativa); se non compilato, si usa
        # quanto letto automaticamente dal PDF.
        descrizione       = oggetto_manuale or dati['descrizione'],
        numero_preventivo = dati['numero_preventivo'],
        data_creazione    = dati['data_emissione'] or datetime.utcnow(),
        data_scadenza     = dati['data_scadenza'],
        importo           = dati['importo'],
        stato             = 'Preventivo',
        file_pdf          = pdf_bytes,
        file_nome         = secure_filename(f.filename),
    )
    db.session.add(nuovo)
    db.session.commit()

    if dati['testo_trovato']:
        pezzi = []
        if dati['numero_preventivo']: pezzi.append(f"n° {dati['numero_preventivo']}")
        if dati['data_emissione']: pezzi.append(f"data {dati['data_emissione'].strftime('%d/%m/%Y')}")
        if dati['data_scadenza']: pezzi.append(f"scadenza {dati['data_scadenza'].strftime('%d/%m/%Y')}")
        if dati['importo']: pezzi.append(f"importo € {dati['importo']:.2f}")
        riepilogo = ", ".join(pezzi) if pezzi else "dati non riconosciuti automaticamente, verificali"
        flash(f"✅ Preventivo archiviato su {cliente.nome} e letto in automatico ({riepilogo}).", "success")
    else:
        flash(f"✅ Preventivo archiviato su {cliente.nome}, ma il PDF non conteneva testo leggibile "
              "(probabile scansione): verifica/completa manualmente numero, data e importo.", "warning")

    return redirect(url_for('dettaglio_cliente', cliente_id=cliente.id))


@app.route('/aggiungi_preventivo', methods=['POST'])
@login_required
def aggiungi_preventivo():
    cliente_id         = request.form.get('cliente_id')
    data_emissione_str = request.form.get('data_emissione')
    data_creazione     = datetime.strptime(data_emissione_str, '%Y-%m-%d') if data_emissione_str else datetime.utcnow()
    p = Preventivo(
        cliente_id        = cliente_id,
        descrizione       = request.form.get('descrizione'),
        numero_preventivo = request.form.get('numero_preventivo'),
        note_revisione    = request.form.get('note_revisione'),
        data_creazione    = data_creazione,
        stato             = 'Preventivo'
    )
    db.session.add(p)
    db.session.commit()
    return redirect(url_for('dashboard'))


@app.route('/cliente/<int:cliente_id>/carica_preventivo_pdf', methods=['POST'])
@login_required
def carica_preventivo_pdf(cliente_id):
    """
    Archivia automaticamente nel CRM la stessa copia PDF del preventivo che
    viene inviata al cliente: numero, data e importo vengono letti dal PDF
    stesso, senza doverli ridigitare a mano nel form della dashboard.
    """
    cliente = Cliente.query.get_or_404(cliente_id)
    f = request.files.get('file_preventivo')
    oggetto_manuale = (request.form.get('oggetto') or '').strip()
    if not f or not f.filename:
        flash('⚠️ Nessun file selezionato.', 'warning')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))

    if not f.filename.lower().endswith('.pdf'):
        flash('⚠️ Carica un file PDF (è lo stesso file che mandi al cliente).', 'warning')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))

    pdf_bytes = f.read()
    try:
        dati = estrai_dati_preventivo_pdf(pdf_bytes)
    except Exception as e:
        flash(f'❌ Errore durante la lettura del PDF: {e}', 'danger')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))

    nuovo = Preventivo(
        cliente_id        = cliente_id,
        # Oggetto scritto a mano da chi carica ha sempre la priorità sul
        # testo letto in automatico dal PDF.
        descrizione       = oggetto_manuale or dati['descrizione'],
        numero_preventivo = dati['numero_preventivo'],
        data_creazione    = dati['data_emissione'] or datetime.utcnow(),
        data_scadenza     = dati['data_scadenza'],
        importo           = dati['importo'],
        stato             = 'Preventivo',
        file_pdf          = pdf_bytes,
        file_nome         = secure_filename(f.filename),
    )
    db.session.add(nuovo)
    db.session.commit()

    # Controllo di sicurezza: la P.IVA letta nel PDF corrisponde a quella
    # anagrafica del cliente sulla cui pagina stiamo caricando il file?
    # (utile per accorgersi subito se il PDF è stato caricato sul cliente sbagliato)
    if dati.get('piva_cliente') and cliente.p_iva and dati['piva_cliente'] != cliente.p_iva:
        flash(f"⚠️ ATTENZIONE: la P.IVA nel PDF ({dati['piva_cliente']}) è diversa da quella "
              f"in anagrafica per {cliente.nome} ({cliente.p_iva}). Controlla di aver caricato "
              f"il PDF sulla scheda cliente giusta.", "warning")

    if dati['testo_trovato']:
        pezzi = []
        if dati['numero_preventivo']: pezzi.append(f"n° {dati['numero_preventivo']}")
        if dati['data_emissione']: pezzi.append(f"data {dati['data_emissione'].strftime('%d/%m/%Y')}")
        if dati['data_scadenza']: pezzi.append(f"scadenza {dati['data_scadenza'].strftime('%d/%m/%Y')}")
        if dati['importo']: pezzi.append(f"importo € {dati['importo']:.2f}")
        riepilogo = ", ".join(pezzi) if pezzi else "dati non riconosciuti automaticamente, verificali"
        flash(f"✅ Preventivo archiviato e letto in automatico ({riepilogo}).", "success")
    else:
        flash("✅ Preventivo archiviato, ma il PDF non conteneva testo leggibile (probabile scansione): "
              "verifica/completa manualmente numero, data e importo.", "warning")

    return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))


@app.route('/preventivo/<int:preventivo_id>/scarica')
@login_required
def scarica_preventivo_pdf(preventivo_id):
    p = Preventivo.query.get_or_404(preventivo_id)
    if not p.file_pdf:
        flash('Nessun PDF archiviato per questo preventivo.', 'warning')
        return redirect(url_for('dettaglio_cliente', cliente_id=p.cliente_id))
    return send_file(
        io.BytesIO(p.file_pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=p.file_nome or f"preventivo_{p.numero_preventivo or p.id}.pdf"
    )


@app.route('/preventivo/<int:preventivo_id>/visualizza')
@login_required
def visualizza_preventivo_pdf(preventivo_id):
    """Apre il PDF direttamente nel browser (nuova scheda), senza forzare
    il download — utile per una rapida occhiata, anche su un preventivo
    archiviato anni prima."""
    p = Preventivo.query.get_or_404(preventivo_id)
    if not p.file_pdf:
        flash('Nessun PDF archiviato per questo preventivo.', 'warning')
        return redirect(url_for('dettaglio_cliente', cliente_id=p.cliente_id))
    return send_file(
        io.BytesIO(p.file_pdf),
        mimetype='application/pdf',
        as_attachment=False,
        download_name=p.file_nome or f"preventivo_{p.numero_preventivo or p.id}.pdf"
    )


@app.route('/elimina_preventivo/<int:id>')
@login_required
def elimina_preventivo(id):
    preventivo = Preventivo.query.get_or_404(id)
    id_cliente = preventivo.cliente_id
    try:
        db.session.delete(preventivo)
        db.session.commit()
        flash('Preventivo rimosso!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Errore: {str(e)}', 'danger')
    return redirect(url_for('dettaglio_cliente', cliente_id=id_cliente))


@app.route('/modifica_preventivo/<int:id>', methods=['POST'])
@login_required
def modifica_preventivo(id):
    preventivo = Preventivo.query.get_or_404(id)
    nuova_desc = request.form.get('descrizione')
    nuova_nota = request.form.get('nota_revisione')
    try:
        if nuova_desc:
            preventivo.descrizione = nuova_desc
        if nuova_nota is not None:
            testo_pulito = nuova_nota.strip()
            preventivo.note_revisione = testo_pulito if testo_pulito else None
        db.session.commit()
        flash('✅ Modifiche salvate!', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'❌ Errore: {str(e)}', 'danger')
    return redirect(url_for('dettaglio_cliente', cliente_id=preventivo.cliente_id))


@app.route('/nota_rapida_pipeline/<int:id>', methods=['POST'])
@login_required
def nota_rapida_pipeline(id):
    p         = Preventivo.query.get_or_404(id)
    nuova_nota= request.form.get('nota_revisione')
    if nuova_nota:
        p.note_revisione = nuova_nota
        db.session.commit()
        flash('Nota aggiornata!', 'info')
    return redirect(url_for('pipeline_preventivi'))


@app.route('/aggiorna_preventivo_veloce/<int:prev_id>', methods=['POST'])
@login_required
def aggiorna_preventivo_veloce(prev_id):
    p                   = Preventivo.query.get_or_404(prev_id)
    nuovo_stato         = request.form.get('nuovo_stato')
    nuova_data_scadenza = request.form.get('data_scadenza')
    if nuovo_stato:
        p.stato                     = nuovo_stato
        p.data_ultimo_aggiornamento = datetime.utcnow()
        if nuovo_stato == 'Sospeso' and nuova_data_scadenza:
            p.data_scadenza = datetime.strptime(nuova_data_scadenza, '%Y-%m-%d')
        db.session.commit()
        flash(f"✅ Preventivo #{p.numero_preventivo} → {nuovo_stato}", "success")
    return redirect(url_for('pipeline_preventivi'))


@app.route('/pipeline_preventivi')
@login_required
def pipeline_preventivi():
    oggi              = datetime.utcnow()
    cliente_id_filtro = request.args.get('cliente_id')
    vista_username    = vista_agente_corrente()
    regione_filtro    = request.args.get('regione', '').strip()
    stati             = ['Preventivo', 'Trattativa', 'Sospeso', 'Ordine', 'Rifiuto']

    # Selettore agente: Angelo/admin vedono tutto (o filtrano per agente/team a
    # scelta), Claudio vede i suoi + i suoi subagenti, un subagente vede solo i
    # propri — stessa logica identica alla dashboard, così ognuno vede in
    # pipeline solo i preventivi dei clienti che gli competono.
    id_clienti_visibili = [c.id for c in
        filtra_query_per_regione(clienti_visibili_query(vista_username), regione_filtro)
        .filter(Cliente.blacklisted == False)
        .with_entities(Cliente.id).all()]

    query = (Preventivo.query.join(Cliente)
             .filter(Cliente.blacklisted == False)
             .filter(Preventivo.cliente_id.in_(id_clienti_visibili)))
    if cliente_id_filtro:
        query = query.filter(Preventivo.cliente_id == cliente_id_filtro)
    tutti_i_preventivi   = query.all()
    preventivi_per_stato = {s: [] for s in stati}
    richiami             = []
    for p in tutti_i_preventivi:
        g_e      = (oggi - p.data_creazione).days
        data_rif = p.data_ultimo_aggiornamento if p.data_ultimo_aggiornamento else p.data_creazione
        g_a      = (oggi - data_rif).days
        is_rosso = (p.stato == 'Preventivo' and g_e >= 7) or (p.stato == 'Trattativa' and g_a >= 3)
        if is_rosso:
            richiami.append(p)
        else:
            if p.stato == 'Ordine':
                if p.data_creazione >= oggi - timedelta(days=30):
                    preventivi_per_stato[p.stato].append(p)
            elif p.stato in preventivi_per_stato:
                preventivi_per_stato[p.stato].append(p)
    # Il menu "Filtra per Cliente" mostra solo i clienti già visibili con la
    # combinazione agente/regione scelta sopra, così i due filtri restano coerenti.
    tutti_i_clienti = (Cliente.query.filter_by(blacklisted=False)
                       .filter(Cliente.id.in_(id_clienti_visibili))
                       .order_by(Cliente.nome).all()) if id_clienti_visibili else []
    return render_template('pipeline_preventivi.html',
        preventivi_per_stato = preventivi_per_stato,
        richiami             = richiami,
        clienti              = tutti_i_clienti,
        cliente_selezionato  = cliente_id_filtro,
        oggi                 = oggi,
        opzioni_vista        = opzioni_vista_menu(),
        vista_corrente       = vista_username,
        opzioni_regione      = opzioni_regione_menu(),
        regione_corrente     = regione_filtro
    )


# ─────────────────────────────────────────────────────────────────
# ROUTE MOBILE — consultazione da smartphone (in viaggio / pre-visita)
# SICUREZZA: tutte le route usano clienti_visibili_query(), quindi da
# cellulare ogni utente vede ESATTAMENTE gli stessi clienti che vede
# da desktop (admin/generale = tutti, capo_area = team + condivisi,
# subagente = assegnati + condivisi). Nessuna scorciatoia.
# ─────────────────────────────────────────────────────────────────

@app.route('/m')
@app.route('/m/clienti')
@login_required
def mobile_clienti():
    """Ricerca clienti ottimizzata per smartphone: campo unico, risultati
    a card grandi tap-friendly. Filtrata con clienti_visibili_query()."""
    q              = (request.args.get('q') or '').strip()
    regione_filtro = (request.args.get('regione') or '').strip()
    query = filtra_query_per_regione(clienti_visibili_query(), regione_filtro).filter(Cliente.blacklisted == False)
    if q:
        like  = f"%{q}%"
        query = query.filter(db.or_(
            Cliente.nome.ilike(like),
            Cliente.provincia.ilike(like),
            Cliente.referente_acquisti.ilike(like),
            Cliente.p_iva.ilike(like)
        ))
    clienti = query.order_by(Cliente.nome).limit(60).all()
    return render_template('mobile_clienti.html', clienti=clienti, q=q,
                           opzioni_regione=opzioni_regione_menu(), regione_corrente=regione_filtro)


@app.route('/m/cliente/<int:cliente_id>')
@login_required
def mobile_cliente(cliente_id):
    """Scheda cliente mobile: tutto ciò che serve PRIMA di entrare in
    azienda — contatti tap-to-call, referente, ultime note, task aperti,
    preventivi in corso. Il cliente deve essere tra quelli visibili
    all'utente loggato (first_or_404 sulla query filtrata)."""
    c    = clienti_visibili_query().filter(Cliente.id == cliente_id).first_or_404()
    oggi = datetime.utcnow()

    note_recenti = sorted(
        c.note, key=lambda n: n.data_inserimento or oggi, reverse=True
    )[:10]
    task_aperti  = sorted(
        [t for t in c.tasks if not t.completato],
        key=lambda t: t.data_scadenza or oggi
    )
    preventivi   = sorted(
        c.preventivi, key=lambda p: p.data_creazione or oggi, reverse=True
    )

    giorni_ultimo_contatto = None
    if c.data_ultimo_contatto:
        giorni_ultimo_contatto = (oggi - c.data_ultimo_contatto).days

    return render_template('mobile_cliente.html',
        cliente                = c,
        note_recenti           = note_recenti,
        task_aperti            = task_aperti,
        preventivi             = preventivi,
        giorni_ultimo_contatto = giorni_ultimo_contatto,
        nome_agente_display    = UTENTI.get(c.agente_username, {}).get('nome_display') if c.agente_username else None,
        oggi                   = oggi
    )


@app.route('/m/cliente/<int:cliente_id>/nota', methods=['POST'])
@login_required
def mobile_nota_rapida(cliente_id):
    """Nota rapida da smartphone (es. appena usciti dalla visita).
    Stessa verifica di visibilità della scheda."""
    c     = clienti_visibili_query().filter(Cliente.id == cliente_id).first_or_404()
    testo = (request.form.get('testo') or '').strip()
    if testo:
        n = NotaColorata(
            cliente_id      = c.id,
            testo           = testo,
            tipo_contatto   = request.form.get('tipo_contatto') or 'Nota Mobile',
            colore          = 'Blu',
            data_inserimento= datetime.utcnow()
        )
        c.data_ultimo_contatto = n.data_inserimento
        db.session.add(n)
        db.session.commit()
        flash('✅ Nota salvata.', 'success')
    return redirect(url_for('mobile_cliente', cliente_id=c.id))


@app.route('/m/pipeline')
@login_required
def mobile_pipeline():
    """Pipeline preventivi mobile: stessa logica di calcolo del desktop
    (richiami rossi: Preventivo fermo >=7gg, Trattativa ferma >=3gg;
    Ordini solo ultimi 30gg) ma limitata ai preventivi dei clienti
    visibili all'utente loggato — coerenza di sicurezza col desktop."""
    oggi           = datetime.utcnow()
    regione_filtro = (request.args.get('regione') or '').strip()
    stati        = ['Preventivo', 'Trattativa', 'Sospeso', 'Ordine', 'Rifiuto']
    visibili_ids = [c.id for c in
                    filtra_query_per_regione(clienti_visibili_query(), regione_filtro)
                    .filter(Cliente.blacklisted == False)
                    .with_entities(Cliente.id).all()]

    tutti_i_preventivi = (Preventivo.query
                          .filter(Preventivo.cliente_id.in_(visibili_ids))
                          .all()) if visibili_ids else []

    preventivi_per_stato = {s: [] for s in stati}
    richiami             = []
    totale_per_stato     = {s: 0 for s in stati}

    for p in tutti_i_preventivi:
        g_e      = (oggi - p.data_creazione).days
        data_rif = p.data_ultimo_aggiornamento if p.data_ultimo_aggiornamento else p.data_creazione
        g_a      = (oggi - data_rif).days
        is_rosso = (p.stato == 'Preventivo' and g_e >= 7) or (p.stato == 'Trattativa' and g_a >= 3)
        if is_rosso:
            richiami.append(p)
        else:
            if p.stato == 'Ordine':
                if p.data_creazione >= oggi - timedelta(days=30):
                    preventivi_per_stato[p.stato].append(p)
            elif p.stato in preventivi_per_stato:
                preventivi_per_stato[p.stato].append(p)

    for s in stati:
        totale_per_stato[s] = sum((p.importo or 0) for p in preventivi_per_stato[s])

    return render_template('mobile_pipeline.html',
        preventivi_per_stato = preventivi_per_stato,
        richiami             = richiami,
        totale_per_stato     = totale_per_stato,
        oggi                 = oggi,
        opzioni_regione      = opzioni_regione_menu(),
        regione_corrente     = regione_filtro
    )


# ─────────────────────────────────────────────────────────────────
# TASK
# ─────────────────────────────────────────────────────────────────

@app.route('/complete_task/<int:task_id>', methods=['POST'])
@login_required
def complete_task(task_id):
    t          = Task.query.get_or_404(task_id)
    nota_esito = request.form.get('nota_esito')
    nuova_data = request.form.get('nuova_scadenza_automatica')
    nuova_desc = request.form.get('nuova_descrizione_automatica')
    t.completato = True
    if nota_esito:
        nuova_nota = NotaColorata(
            cliente_id    = t.cliente_id,
            testo         = nota_esito,
            tipo_contatto = 'Task Chiuso',
            colore        = 'Verde'
        )
        db.session.add(nuova_nota)
        t.cliente.data_ultimo_contatto = datetime.utcnow()
    if nuova_data:
        try:
            nuovo_task = Task(
                cliente_id    = t.cliente_id,
                descrizione   = nuova_desc if nuova_desc else f"Recall post: {nota_esito}",
                data_scadenza = datetime.strptime(nuova_data, '%Y-%m-%d'),
                completato    = False
            )
            db.session.add(nuovo_task)
            flash(f"✅ Task chiuso, nuovo rinvio per il {nuova_data}", "success")
        except Exception:
            flash("⚠️ Task chiuso, errore formato data rinvio", "danger")
    db.session.commit()
    return redirect(request.referrer or url_for('dashboard'))


@app.route('/elimina_task/<int:id>', methods=['POST'])
@login_required
def elimina_task(id):
    pin = request.form.get('pin_segreto')
    if pin == '1234':
        task       = Task.query.get_or_404(id)
        cliente_id = task.cliente_id
        db.session.delete(task)
        db.session.commit()
        flash('✅ Task rimosso!', 'success')
        return redirect(url_for('dettaglio_cliente', cliente_id=cliente_id))
    flash('⚠️ PIN ERRATO!', 'danger')
    return redirect(request.referrer)


# ─────────────────────────────────────────────────────────────────
# IMPORT / EXPORT
# ─────────────────────────────────────────────────────────────────

ALIAS_COLONNE_LEAD = {
    'nome':               ['nome', 'azienda', 'ragione sociale', 'ragionesociale', 'cliente', 'denominazione', 'società', 'societa'],
    'email':              ['email', 'e-mail', 'mail', 'e mail'],
    'telefono':           ['telefono', 'tel', 'cellulare', 'cell', 'numero'],
    'p_iva':              ['p_iva', 'piva', 'p.iva', 'partita iva', 'partita_iva'],
    'provincia':          ['provincia', 'prov'],
    'referente_acquisti': ['referente_acquisti', 'referente', 'contatto', 'referente acquisti'],
}

def _leggi_excel_lead(file_storage):
    """Legge il file Excel caricato individuando automaticamente la riga di
    intestazione (anche se preceduta da righe di titolo/istruzioni) e
    rinominando le colonne riconosciute secondo lo schema del CRM."""
    raw = pd.read_excel(file_storage, header=None)
    tutti_alias_nome = set(ALIAS_COLONNE_LEAD['nome'])
    riga_intestazione = 0
    for i in range(min(10, len(raw))):
        valori = set(str(v).strip().lower() for v in raw.iloc[i].tolist() if pd.notna(v))
        if valori & tutti_alias_nome:
            riga_intestazione = i
            break
    intestazioni = [str(v).strip().lower() for v in raw.iloc[riga_intestazione].tolist()]
    df = raw.iloc[riga_intestazione + 1:].copy()
    df.columns = intestazioni
    # Rinomina le colonne riconosciute secondo gli alias
    mappa_rinomina = {}
    for standard, alias_list in ALIAS_COLONNE_LEAD.items():
        for col in df.columns:
            if col in alias_list and col != standard:
                mappa_rinomina[col] = standard
                break
    df = df.rename(columns=mappa_rinomina)
    return df


@app.route('/upload_lead', methods=['POST'])
@login_required
def upload_lead():
    file = request.files.get('file_lead')
    if file:
        try:
            df = _leggi_excel_lead(file)
            if 'nome' not in df.columns:
                flash("❌ Errore importazione: non trovo una colonna 'Nome'/'Azienda'/'Ragione Sociale' nel file. Controlla l'intestazione.")
                return redirect(url_for('dashboard'))
            nuovi_inseriti = 0
            for _, row in df.iterrows():
                nome_val  = str(row.get('nome', '')).strip()
                p_iva_val = str(row.get('p_iva', '')).strip().split('.')[0]
                if p_iva_val.lower() in ['nan', '', 'none']:
                    p_iva_val = None
                elif p_iva_val.isdigit() and len(p_iva_val) < 11:
                    p_iva_val = p_iva_val.zfill(11)
                if not nome_val or nome_val.lower() == 'nan':
                    continue
                esistente = Cliente.query.filter_by(p_iva=p_iva_val).first() if p_iva_val else Cliente.query.filter(Cliente.nome.ilike(nome_val)).first()
                if not esistente:
                    nuovo = Cliente(
                        nome               = nome_val,
                        p_iva              = p_iva_val,
                        telefono           = str(row.get('telefono', '')) if str(row.get('telefono', '')).strip().lower() not in ('', 'nan') else None,
                        email              = str(row.get('email', '')) if str(row.get('email', '')).strip().lower() not in ('', 'nan') else None,
                        provincia          = str(row.get('provincia', '')).strip().upper()[:2],
                        referente_acquisti = str(row.get('referente_acquisti', '')).strip() if str(row.get('referente_acquisti', '')).strip().lower() not in ('', 'nan') else '',
                        tipo_anagrafica    = 'Lead'
                    )
                    db.session.add(nuovo)
                    nuovi_inseriti += 1
            db.session.commit()
            flash(f"✅ Importazione completata: {nuovi_inseriti} nuovi lead.")
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Errore importazione: {str(e)}")
    return redirect(url_for('dashboard'))


@app.route('/upload_excel', methods=['GET', 'POST'])
@login_required
def upload_excel():
    if request.method == 'GET':
        return render_template('upload_form.html')
    file = request.files.get('file')
    if file:
        try:
            df = pd.read_excel(file)
            df.columns = df.columns.str.strip().str.lower()
            aggiornati = 0
            for _, row in df.iterrows():
                p_iva_excel = str(row.get('p_iva', '')).strip().split('.')[0]
                if p_iva_excel and p_iva_excel.lower() != 'nan':
                    p_iva_excel = p_iva_excel.zfill(11)
                    c           = Cliente.query.filter(Cliente.p_iva.like(f"{p_iva_excel}%")).first()
                    nuova_data  = pd.to_datetime(row.get('data_fattura'), errors='coerce')
                    if c and pd.notnull(nuova_data):
                        c.p_iva                = p_iva_excel
                        c.ultima_data_acquisto = nuova_data.to_pydatetime()
                        c.tipo_anagrafica      = 'Cliente'
                        aggiornati += 1
            db.session.commit()
            flash(f"✅ {aggiornati} clienti aggiornati." if aggiornati else "⚠️ Nessun cliente trovato.")
        except Exception as e:
            db.session.rollback()
            flash(f"❌ Errore: {str(e)}")
    return redirect(url_for('dashboard'))


@app.route('/importa_excel_mail', methods=['POST'])
@login_required
def importa_excel_mail():
    file = request.files.get('file_excel')
    if file:
        df = pd.read_excel(file)
        for _, row in df.iterrows():
            nome_ente = str(row['ente']).strip().upper()
            cliente   = Cliente.query.filter_by(nome=nome_ente).first()
            if not cliente:
                cliente = Cliente(nome=nome_ente, tipo_anagrafica='Lead')
                db.session.add(cliente)
                db.session.flush()
            nuova_nota = NotaColorata(
                cliente_id    = cliente.id,
                testo         = f"CARICAMENTO EXCEL: {row['materia']}",
                tipo_contatto = "Importazione",
                colore        = "Grigio"
            )
            db.session.add(nuova_nota)
        db.session.commit()
        flash("Excel importato!")
    return redirect(url_for('dashboard'))


@app.route('/bonifica_database')
@admin_required
def bonifica_database():
    try:
        clienti   = Cliente.query.all()
        contatore = 0
        for c in clienti:
            if c.p_iva:
                p_iva_pulita = str(c.p_iva).strip().split('.')[0]
                if p_iva_pulita.isdigit() and len(p_iva_pulita) < 11:
                    p_iva_pulita = p_iva_pulita.zfill(11)
                if c.p_iva != p_iva_pulita:
                    c.p_iva = p_iva_pulita
                    contatore += 1
        db.session.commit()
        flash(f"✅ Bonifica completata: {contatore} P.IVA sistemate.")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Errore: {str(e)}")
    return redirect(url_for('dashboard'))


@app.route('/export_tasks')
@login_required
def export_tasks():
    user_agent = request.headers.get('User-Agent', '').lower()
    if 'qt' in user_agent or 'webview' in user_agent or 'fp' in user_agent:
        webbrowser.open(f"http://127.0.0.1:5000{url_for('export_tasks')}")
        return '', 204
    tasks      = Task.query.filter_by(completato=False).all()
    lista_tasks= [{
        'Cliente':     t.cliente.nome if t.cliente else 'N/D',
        'Descrizione': t.descrizione,
        'Scadenza':    t.data_scadenza.strftime('%d/%m/%Y') if t.data_scadenza else 'N/D'
    } for t in tasks]
    if not lista_tasks:
        return "Nessun task da esportare", 400
    df     = pd.DataFrame(lista_tasks)
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Task_Aperti')
    output.seek(0)
    return send_file(output,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True, download_name="export_task.xlsx")


@app.route('/backup_migrazione_totale')
@admin_required
def backup_migrazione_totale():
    user_agent = request.headers.get('User-Agent', '').lower()
    if 'qt' in user_agent or 'webview' in user_agent or 'fp' in user_agent:
        webbrowser.open(f"http://127.0.0.1:5000{url_for('backup_migrazione_totale')}")
        return '', 204
    try:
        clienti    = Cliente.query.all()
        preventivi = Preventivo.query.all()
        note       = NotaColorata.query.all()
        tasks      = Task.query.all()
        df_clienti = pd.DataFrame([{
            'ID': c.id, 'Nome': c.nome, 'P.IVA': c.p_iva, 'Tipo': c.tipo_anagrafica,
            'Email': c.email, 'Tel': c.telefono, 'Prov': c.provincia,
            'Referente': c.referente_acquisti, 'Blacklist': c.blacklisted,
            'Data Creazione': c.data_creazione.strftime('%d/%m/%Y') if c.data_creazione else ''
        } for c in clienti])
        df_preventivi = pd.DataFrame([{
            'ID_Prev': p.id, 'Cliente': p.cliente.nome, 'Oggetto': p.descrizione,
            'Stato': p.stato, 'N_Prev': p.numero_preventivo, 'N_Ordine': p.numero_ordine,
            'Note': p.note_revisione,
            'Data': p.data_creazione.strftime('%d/%m/%Y') if p.data_creazione else ''
        } for p in preventivi])
        df_note = pd.DataFrame([{
            'Data':    n.data_inserimento.strftime('%d/%m/%Y %H:%M') if n.data_inserimento else '',
            'Cliente': n.cliente.nome, 'Tipo': n.tipo_contatto, 'Testo': n.testo
        } for n in note])
        df_tasks = pd.DataFrame([{
            'Cliente':    t.cliente.nome if t.cliente else 'N/D',
            'Descrizione':t.descrizione,
            'Scadenza':   t.data_scadenza.strftime('%d/%m/%Y') if t.data_scadenza else '',
            'Completato': 'SÌ' if t.completato else 'NO'
        } for t in tasks])
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_clienti.to_excel(writer,    sheet_name='ANAGRAFICA',        index=False)
            df_preventivi.to_excel(writer, sheet_name='PREVENTIVI_ORDINI', index=False)
            df_note.to_excel(writer,       sheet_name='STORICO_ATTIVITA',  index=False)
            df_tasks.to_excel(writer,      sheet_name='TASK_SCADENZE',     index=False)
        output.seek(0)
        return send_file(output,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
            as_attachment=True,
            download_name=f"BACKUP_MGC_CRM_{datetime.now().strftime('%Y%m%d')}.xlsx")
    except Exception as e:
        return f"Errore: {str(e)}", 500


@app.route('/export_lead_recenti', methods=['POST'])
@login_required
def export_lead_recenti():
    data_inizio_str = request.form.get('data_inizio')
    if not data_inizio_str:
        return redirect(url_for('dashboard'))
    data_inizio = datetime.strptime(data_inizio_str, '%Y-%m-%d')
    leads       = Cliente.query.filter(
        Cliente.tipo_anagrafica == 'Lead',
        Cliente.data_creazione  >= data_inizio
    ).all()
    df     = pd.DataFrame([{
        'Nome': l.nome, 'P.IVA': l.p_iva,
        'Data Inserimento': l.data_creazione.strftime('%d/%m/%Y')
    } for l in leads])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    return send_file(output, download_name=f"Lead_dal_{data_inizio_str}.xlsx", as_attachment=True)


@app.route('/export_attivita_cliente/<int:cliente_id>')
@login_required
def export_attivita_cliente(cliente_id):
    user_agent = request.headers.get('User-Agent', '').lower()
    if 'qt' in user_agent or 'webview' in user_agent or 'fp' in user_agent:
        webbrowser.open(f"http://127.0.0.1:5000{url_for('export_attivita_cliente', cliente_id=cliente_id)}")
        return '', 204
    cliente = Cliente.query.get_or_404(cliente_id)
    note    = NotaColorata.query.filter_by(cliente_id=cliente_id).order_by(NotaColorata.data_inserimento.desc()).all()
    if not note:
        return "<h1>Nessuna attività da esportare</h1>", 400
    df     = pd.DataFrame([{
        'Data': n.data_inserimento.strftime('%d/%m/%Y %H:%M') if n.data_inserimento else '',
        'Tipo': n.tipo_contatto, 'Esito/Nota': n.testo
    } for n in note])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Attivita')
    output.seek(0)
    return send_file(output,
        download_name=f"Attivita_{cliente.nome.replace(' ', '_')}.xlsx",
        as_attachment=True,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')


# ─────────────────────────────────────────────────────────────────
# MARKETING / BUSINESS INTELLIGENCE
# ─────────────────────────────────────────────────────────────────

@app.route('/business_intelligence')
@app.route('/bi_marketing')
@login_required
def business_intelligence():
    try:
        tot_target   = Cliente.query.filter(
            Cliente.tipo_anagrafica.in_(['Lead', 'Prospect']),
            Cliente.blacklisted == False
        ).count()
        aperture     = Cliente.query.filter_by(mail_aperta=True,         blacklisted=False).count()
        download_oro = Cliente.query.filter_by(download_effettuato=True, blacklisted=False).count()
        oro_senza_prev = Cliente.query.filter_by(download_effettuato=True).filter(~Cliente.preventivi.any()).count()
        tasso_apertura = round((aperture     / tot_target * 100), 1) if tot_target > 0 else 0
        tasso_oro      = round((download_oro / tot_target * 100), 1) if tot_target > 0 else 0

        clienti_storici_ids = [c.id for c in Cliente.query.filter_by(tipo_anagrafica='Cliente').all()]
        prev_difesa   = Preventivo.query.filter(Preventivo.cliente_id.in_(clienti_storici_ids)).count() if clienti_storici_ids else 0
        ordini_difesa = Preventivo.query.filter(Preventivo.cliente_id.in_(clienti_storici_ids), Preventivo.stato == 'Ordine').count() if clienti_storici_ids else 0
        cr_difesa     = round((ordini_difesa / prev_difesa * 100), 1) if prev_difesa > 0 else 0

        prev_attacco   = Preventivo.query.filter(~Preventivo.cliente_id.in_(clienti_storici_ids)).count() if clienti_storici_ids else Preventivo.query.count()
        ordini_attacco = Preventivo.query.filter(~Preventivo.cliente_id.in_(clienti_storici_ids), Preventivo.stato == 'Ordine').count() if clienti_storici_ids else Preventivo.query.filter_by(stato='Ordine').count()
        cr_attacco     = round((ordini_attacco / prev_attacco * 100), 1) if prev_attacco > 0 else 0

        top_province = db.session.query(Cliente.provincia, func.count(Cliente.id)).\
            filter(Cliente.download_effettuato == True).\
            group_by(Cliente.provincia).\
            order_by(func.count(Cliente.id).desc()).limit(5).all()

        stats = {
            'fuel':    {'totale': tot_target, 'aperture': aperture, 'tasso_apertura': tasso_apertura,
                        'oro': download_oro, 'tasso_oro': tasso_oro, 'pronti': oro_senza_prev},
            'difesa':  {'preventivi': prev_difesa,  'ordini': ordini_difesa,  'cr': cr_difesa},
            'attacco': {'preventivi': prev_attacco, 'ordini': ordini_attacco, 'cr': cr_attacco},
            'top_province': top_province
        }
        return render_template('bi_marketing.html', stats=stats)
    except Exception as e:
        return f"Errore BI: {str(e)}"


@app.route('/marketing_ai')
@direzione_required
def marketing_ai():
    oggi  = datetime.utcnow()
    tutti = Cliente.query.filter_by(blacklisted=False).all()
    clienti_lista_rossa = []
    for c in tutti:
        if not c.email:
            continue
        if c.data_prossimo_contatto:
            if c.data_prossimo_contatto <= oggi:
                clienti_lista_rossa.append(c)
        else:
            soglia     = c.frequenza_ricontatto or 60
            limite     = oggi - timedelta(days=soglia)
            u_acquisto = c.ultima_data_acquisto or datetime.min
            u_contatto = c.data_ultimo_contatto or datetime.min
            if u_acquisto <= limite and u_contatto <= limite:
                clienti_lista_rossa.append(c)

    if not clienti_lista_rossa:
        clienti_lista_rossa = Cliente.query.filter(
            Cliente.blacklisted == False,
            Cliente.email.isnot(None), Cliente.email != '',
            Cliente.tipo_anagrafica.in_(['Cliente', 'Prospect'])
        ).order_by(Cliente.nome).all()

    tutti_con_email = Cliente.query.filter(
        Cliente.blacklisted == False,
        Cliente.email.isnot(None), Cliente.email != ''
    ).order_by(Cliente.nome).all()

    proposte = [{
        'id':          c.id,
        'nome':        c.nome,
        'email':       c.email,
        'ultima_data': c.data_ultimo_contatto.strftime('%d/%m/%Y') if c.data_ultimo_contatto else 'Mai',
        'testo':       ''
    } for c in clienti_lista_rossa]

    return render_template('marketing_ai.html',
        proposte              = proposte,
        tutti_clienti         = tutti_con_email,
        totale_lista_rossa    = len(clienti_lista_rossa),
        totale_con_email      = len(tutti_con_email),
        tab                   = request.args.get('tab', 'email-ai')
    )


@app.route('/market_radar')
@direzione_required
def market_radar():
    import re
    vip      = Cliente.query.filter_by(tipo_anagrafica='Cliente', blacklisted=False).order_by(Cliente.nome).limit(8).all()
    nomi_vip = []
    for c in vip:
        nome_pulito = re.sub(r'\b(S\.?R\.?L\.?|S\.?P\.?A\.?|S\.?C\.?A\.?R\.?L\.?|S\.?N\.?C\.?)\b', '', c.nome, flags=re.IGNORECASE).strip()
        if nome_pulito:
            nomi_vip.append(nome_pulito)
    return render_template('market_radar.html', clienti_vip=nomi_vip)


@app.route('/calendario_scadenze')
@login_required
def calendario_scadenze():
    from datetime import date as _date
    import calendar as cal_mod
    oggi       = datetime.utcnow()
    anno       = int(request.args.get('anno', oggi.year))
    mese       = int(request.args.get('mese', oggi.month))
    cal        = calendar.Calendar(firstweekday=0)
    giorni_mese= cal.monthdayscalendar(anno, mese)
    nome_mese  = ["Gennaio","Febbraio","Marzo","Aprile","Maggio","Giugno",
                  "Luglio","Agosto","Settembre","Ottobre","Novembre","Dicembre"][mese - 1]

    tasks = Task.query.filter(Task.completato == False).all()
    mappa_tasks = {}
    for t in tasks:
        if t.data_scadenza and t.data_scadenza.month == mese and t.data_scadenza.year == anno:
            g = t.data_scadenza.day
            if g not in mappa_tasks:
                mappa_tasks[g] = []
            mappa_tasks[g].append(t)

    mappa_visite = {}

    return render_template('calendario_visuale.html',
        giorni_mese=giorni_mese, mappa_tasks=mappa_tasks,
        mappa_visite={},
        nome_mese=nome_mese, anno=anno, mese=mese, oggi=oggi)


# ─────────────────────────────────────────────────────────────────
# MAIL INTELLIGENCE
# ─────────────────────────────────────────────────────────────────

@app.route('/mail_intelligence')
@direzione_required
def mail_intelligence():
    try:
        alert_negativi = EmailAlert.query.filter_by(sentiment='Negativo').order_by(EmailAlert.urgenza.desc()).all()
        alert_positivi = EmailAlert.query.filter_by(sentiment='Positivo').order_by(EmailAlert.data_ricezione.desc()).all()
        alert_neutri   = EmailAlert.query.filter_by(sentiment='Neutro').order_by(EmailAlert.data_ricezione.desc()).all()
        return render_template('mail_intelligence.html',
            alert_negativi=alert_negativi,
            alert_positivi=alert_positivi,
            alert_neutri=alert_neutri)
    except Exception as e:
        return f"Errore Mail Intelligence: {str(e)}"


@app.route('/sync_mails_now')
@admin_required
def sync_mails_now():
    try:
        sync_email_intelligence()
        return redirect(url_for('mail_intelligence'))
    except Exception as e:
        return f"Errore sync: {str(e)}"


@app.route('/elimina_alert/<int:id>', methods=['POST'])
@login_required
def elimina_alert(id):
    alert = EmailAlert.query.get_or_404(id)
    db.session.delete(alert)
    db.session.commit()
    return redirect(url_for('mail_intelligence'))


@app.route('/reset_definitivo')
@admin_required
def reset_definitivo():
    try:
        n = db.session.query(EmailAlert).delete()
        db.session.commit()
        return f"🔥 RESET: Cancellate {n} email."
    except Exception as e:
        db.session.rollback()
        return f"❌ Errore: {str(e)}"


# ─────────────────────────────────────────────────────────────────
# API MAILCHIMP (invio email ai clienti CRM)
# ─────────────────────────────────────────────────────────────────

@app.route('/api/invia_mailchimp', methods=['POST'])
@login_required
def api_invia_mailchimp():
    data        = request.json
    email_dest  = data.get('email')
    nome        = data.get('nome')
    testo_email = data.get('testo')
    if not email_dest or not testo_email:
        return jsonify({"status": "error", "message": "Dati mancanti"}), 400
    try:
        mailchimp_client.lists.set_list_member(MAILCHIMP_LIST_ID, email_dest, {
            "email_address": email_dest, "status_if_new": "subscribed",
            "merge_fields": {"FNAME": nome, "LNAME": "CRM"}
        })
        campagna = mailchimp_client.campaigns.create({
            "type": "regular",
            "recipients": {
                "list_id": MAILCHIMP_LIST_ID,
                "segment_opts": {"match": "all", "conditions": [
                    {"condition_type": "EmailAddress", "field": "EMAIL", "op": "is", "value": email_dest}
                ]}
            },
            "settings": {
                "subject_line": f"Proposta per {nome} - {AZIENDA_NOME}",
                "from_name":    AZIENDA_NOME,
                "reply_to":     AZIENDA_EMAIL,
                "authenticate": True
            }
        })
        mailchimp_client.campaigns.set_content(campagna["id"], {
            "html": f"<div style='font-family:sans-serif;'>{testo_email.replace(chr(10), '<br>')}</div>"
        })
        mailchimp_client.campaigns.send(campagna["id"])
        cliente = Cliente.query.filter_by(email=email_dest).first()
        if cliente:
            if cliente.tipo_anagrafica == 'Lead':
                cliente.tipo_anagrafica = 'Prospect'
            cliente.data_ultimo_contatto = datetime.utcnow()
            db.session.add(NotaColorata(
                cliente_id     = cliente.id,
                testo          = f"🚀 Mail inviata via Mailchimp il {datetime.now().strftime('%d/%m/%Y %H:%M')}",
                tipo_contatto  = "Email Marketing AI",
                colore         = "purple",
                data_inserimento= datetime.utcnow()
            ))
            db.session.commit()
        return jsonify({"status": "success", "message": f"✅ Mail inviata a {nome}!"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 400


@app.route('/api/invia_tutti_mailchimp', methods=['POST'])
@login_required
def api_invia_tutti_mailchimp():
    data     = request.json
    proposte = data.get('proposte', [])
    inviati  = 0
    errori   = 0
    for p in proposte:
        try:
            email_dest = p.get('email')
            nome       = p.get('nome')
            testo      = p.get('testo')
            mailchimp_client.lists.set_list_member(MAILCHIMP_LIST_ID, email_dest, {
                "email_address": email_dest, "status_if_new": "subscribed",
                "merge_fields": {"FNAME": nome, "LNAME": "CRM"}
            })
            cliente = Cliente.query.filter_by(email=email_dest).first()
            if cliente:
                if cliente.tipo_anagrafica == 'Lead':
                    cliente.tipo_anagrafica = 'Prospect'
                cliente.data_ultimo_contatto = datetime.utcnow()
                db.session.add(NotaColorata(
                    cliente_id    = cliente.id,
                    testo         = f"📧 INVIO MASSIVO: {testo[:100]}...",
                    tipo_contatto = "Marketing Massivo",
                    colore        = "Viola"
                ))
                inviati += 1
        except Exception as e:
            print(f"Errore su {p.get('nome')}: {e}")
            errori += 1
    db.session.commit()
    return jsonify({"status": "success", "message": f"✅ {inviati} inviati, {errori} errori."})


@app.route('/api/sync_mailchimp_stats')
@login_required
def sync_mailchimp_stats():
    try:
        import hashlib
        aggiornati = 0
        prospects  = Cliente.query.filter_by(tipo_anagrafica='Prospect').all()
        for p in prospects:
            if not p.email: continue
            try:
                email_hash = hashlib.md5(p.email.lower().encode()).hexdigest()
                response   = mailchimp_client.lists.get_list_member_activity(MAILCHIMP_LIST_ID, email_hash)
                ha_aperto  = any(act.get('action') == 'open' for act in response.get('activity', []))
                if ha_aperto and not p.mail_aperta:
                    p.mail_aperta = True
                    db.session.add(NotaColorata(
                        cliente_id    = p.id,
                        testo         = "🔥 APERTURA RILEVATA: Il cliente ha letto la mail!",
                        tipo_contatto = "Mailchimp Sync", colore = "Verde"
                    ))
                    aggiornati += 1
            except Exception:
                continue
        db.session.commit()
        return jsonify({"status": "success", "message": f"✅ Sync: {aggiornati} novità."})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


# ─────────────────────────────────────────────────────────────────
# API AI
# ─────────────────────────────────────────────────────────────────

@app.route('/api/test_gemini')
def test_gemini():
    try:
        response = client_ai.models.generate_content(model=MODELLO_ATTUALE, contents="Rispondi solo: OK GEMINI FUNZIONA")
        return jsonify({"status": "ok", "risposta": response.text.strip()})
    except Exception as e:
        return jsonify({"status": "error", "errore": str(e)}), 500


@app.route('/api/genera_email_singola', methods=['POST'])
@direzione_required
def genera_email_singola():
    data       = request.json
    nome       = data.get('nome', '')
    prompt = (
        f"Agisci come assistente commerciale di {AZIENDA_NOME} ({AZIENDA_SITO}). "
        f"Scrivi una mail commerciale B2B personalizzata per {nome}. "
        "REGOLE:\n1. Inizia direttamente con 'Oggetto:'\n"
        f"2. Saluto: 'Spett.le {nome},'\n"
        "3. Tono: Professionale e diretto.\n"
        f"4. Firma: '{AZIENDA_FIRMA}'.\n"
        "5. NO parentesi quadre. SOLO il testo della mail.\n"
        f"6. Invita a scoprire i servizi: https://{AZIENDA_SITO}\n"
        "7. MAX 150 parole."
    )
    try:
        response = client_ai.models.generate_content(model=MODELLO_ATTUALE, contents=prompt)
        return jsonify({"status": "ok", "testo": response.text.strip()})
    except Exception as e:
        return jsonify({"status": "error", "testo": f"[Errore AI: {str(e)[:80]}]"}), 500


@app.route('/api/check_duplicate')
@login_required
def check_duplicate():
    nome_cercato = request.args.get('nome', '').strip()
    esiste       = Cliente.query.filter(Cliente.nome.ilike(f"%{nome_cercato}%")).first()
    return jsonify({"exists": bool(esiste)})


@app.route('/api/importa_lead_massivo', methods=['POST'])
@login_required
def importa_lead_massivo():
    data           = request.json
    leads_ricevuti = data.get('leads', [])
    nuovi_count    = duplicati_count = 0
    for l in leads_ricevuti:
        nome_pulito = l.get('nome', '').strip().upper()
        if not nome_pulito:
            continue
        esistente = Cliente.query.filter(Cliente.nome.ilike(nome_pulito)).first()
        if esistente:
            duplicati_count += 1
            continue
        nuovo = Cliente(
            nome               = nome_pulito,
            p_iva              = l.get('p_iva'),
            telefono           = l.get('telefono') if l.get('telefono') != 'N.D.' else None,
            email              = l.get('email') if l.get('email') != 'N.D.' else None,
            provincia          = l.get('provincia', 'PG').strip().upper()[:2],
            referente_acquisti = "DA RADAR",
            tipo_anagrafica    = 'Lead'
        )
        db.session.add(nuovo)
        nuovi_count += 1
    try:
        db.session.commit()
        return jsonify({"status": "success", "nuovi": nuovi_count, "duplicati": duplicati_count}), 200
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500




# ─────────────────────────────────────────────────────────────────
# API CONTENT FACTORY — PED e Clienti
# ─────────────────────────────────────────────────────────────────

@app.route('/api/get_ped')
@login_required
def get_ped():
    """Restituisce il piano editoriale al Content Factory."""
    records = EditorialPlan.query.order_by(EditorialPlan.data.asc()).all()
    return jsonify([r.to_dict() for r in records])


@app.route('/api/save_ped', methods=['POST'])
@login_required
def save_ped():
    """Salva/sostituisce il piano editoriale ricevuto dal Content Factory."""
    try:
        dati = request.json
        if not isinstance(dati, list):
            return jsonify({"status": "error", "message": "Formato atteso: lista JSON"}), 400
        # Cancella il piano esistente e reinserisce
        EditorialPlan.query.delete()
        for item in dati:
            record = EditorialPlan(
                data   = item.get('Data',   ''),
                canale = item.get('Canale', ''),
                tipo   = item.get('Tipo',   ''),
                titolo = item.get('Titolo', ''),
                brief  = item.get('Brief',  ''),
                stato  = item.get('Stato',  '⏳ Pianificato'),
            )
            db.session.add(record)
        db.session.commit()
        return jsonify({"status": "success", "salvati": len(dati)})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/update_post_status', methods=['POST'])
@login_required
def update_post_status():
    """Aggiorna lo stato di un singolo post del PED."""
    try:
        data   = request.json
        record = EditorialPlan.query.get(data.get('id'))
        if not record:
            return jsonify({"status": "error", "message": "Record non trovato"}), 404
        record.stato                = data.get('stato', record.stato)
        record.ultimo_aggiornamento = datetime.utcnow()
        db.session.commit()
        return jsonify({"status": "success"})
    except Exception as e:
        db.session.rollback()
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/genera_piano_editoriale_ia', methods=['POST'])
@direzione_required
def genera_piano_editoriale_ia_route():
    """Genera con Gemini il piano editoriale del mese e lo aggiunge al DB."""
    tema_mese  = request.form.get('tema_mese', 'Innovazione nelle PMI').strip()
    obiettivo  = request.form.get('obiettivo', 'Brand Awareness').strip()
    frequenza  = int(request.form.get('frequenza', 3))
    mese_label = datetime.utcnow().strftime('%B %Y')

    if client_ai is None:
        flash("⚠️ Funzione IA non disponibile: manca la variabile GOOGLE_API_KEY su Railway.", "warning")
        return redirect(url_for('marketing_ai', tab='editorial'))

    try:
        piano = genera_piano_editoriale_ia(
            client_ai, MODELLO_ATTUALE, tema_mese, obiettivo, frequenza, mese_label
        )
        for item in piano:
            record = EditorialPlan(
                data   = item.get('Data',   ''),
                canale = item.get('Canale', ''),
                tipo   = item.get('Tipo',   ''),
                titolo = item.get('Titolo', ''),
                brief  = item.get('Brief',  ''),
                stato  = '⏳ Pianificato',
            )
            db.session.add(record)
        db.session.commit()
        flash(f"✅ Piano editoriale generato: {len(piano)} contenuti aggiunti.", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"❌ Errore nella generazione del piano: {e}", "danger")

    return redirect(url_for('marketing_ai', tab='editorial'))


@app.route('/api/genera_campagna_ads', methods=['POST'])
@direzione_required
def api_genera_campagna_ads():
    """Genera testo + immagine per una campagna pubblicitaria (Instagram/LinkedIn)."""
    if client_ai is None:
        return jsonify({"status": "error", "message": "IA non disponibile: manca GOOGLE_API_KEY su Railway."}), 503
    try:
        dati      = request.json or {}
        argomento = (dati.get('argomento') or '').strip()
        canale    = dati.get('canale', 'Instagram')
        if not argomento:
            return jsonify({"status": "error", "message": "Argomento mancante"}), 400

        risultato = genera_campagna_ads(client_ai, MODELLO_ATTUALE, argomento, canale)
        immagine_b64 = base64.b64encode(risultato['immagine_bytes']).decode('utf-8')

        return jsonify({
            "status": "success",
            "testo": risultato['testo'],
            "immagine_base64": immagine_b64,
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route('/api/genera_video_reel', methods=['POST'])
@direzione_required
def api_genera_video_reel():
    """
    Crea un Reel video da 3 media (gancio/corpo/cta) + audio caricati dall'utente.
    Riceve multipart/form-data:
      - file "media_0", "media_1", "media_2" (foto o mp4, almeno uno)
      - file "audio"
      - campi "testo_gancio", "testo_cta"
      - campo "orientamento" ('verticale' default, 'orizzontale' per 16:9)
    Ritorna il file mp4 generato come allegato scaricabile.
    """
    temp_dir = tempfile.mkdtemp(prefix="reel_upload_")
    media_paths = []
    try:
        for key in ('media_0', 'media_1', 'media_2'):
            f = request.files.get(key)
            if f and f.filename:
                p = os.path.join(temp_dir, secure_filename(f.filename))
                f.save(p)
                media_paths.append(p)
            else:
                media_paths.append(None)

        audio_file = request.files.get('audio')
        if not audio_file or not audio_file.filename:
            return jsonify({"status": "error", "message": "Audio mancante"}), 400
        audio_path = os.path.join(temp_dir, secure_filename(audio_file.filename))
        audio_file.save(audio_path)

        testi = {
            'gancio': request.form.get('testo_gancio', ''),
            'cta':    request.form.get('testo_cta', ''),
        }
        is_horizontal = request.form.get('orientamento', 'verticale') == 'orizzontale'

        video_bytes = genera_video_reel(media_paths, audio_path, testi, is_horizontal)

        return send_file(
            io.BytesIO(video_bytes),
            mimetype='video/mp4',
            as_attachment=True,
            download_name=f"reel_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.mp4"
        )
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        for fn in os.listdir(temp_dir):
            try:
                os.remove(os.path.join(temp_dir, fn))
            except OSError:
                pass
        try:
            os.rmdir(temp_dir)
        except OSError:
            pass


@app.route('/api/clienti_lista')
@login_required
def api_clienti_lista():
    """Restituisce la lista clienti al Content Factory per invio massivo."""
    con_email = request.args.get('con_email', 'false').lower() == 'true'
    query     = Cliente.query.filter_by(blacklisted=False)
    if con_email:
        query = query.filter(Cliente.email.isnot(None), Cliente.email != '')
    clienti = query.order_by(Cliente.nome.asc()).all()
    return jsonify([{
        'id':    c.id,
        'nome':  c.nome,
        'email': c.email,
        'tipo':  c.tipo_anagrafica,
    } for c in clienti])

# ─────────────────────────────────────────────────────────────────
# DOWNLOAD CATALOGO
# ─────────────────────────────────────────────────────────────────

@app.route('/download_catalogo/<int:cliente_id>')
def download_catalogo(cliente_id):
    import hashlib
    cliente = Cliente.query.get_or_404(cliente_id)
    cliente.download_effettuato = True
    nuova_nota = NotaColorata(
        cliente_id     = cliente.id,
        testo          = "✨ ORO: Catalogo scaricato dal link email.",
        tipo_contatto  = "Download", colore = "Oro",
        data_inserimento= datetime.utcnow()
    )
    if cliente.tipo_anagrafica == 'Lead':
        cliente.tipo_anagrafica = 'Prospect'
    try:
        email_hash = hashlib.md5(cliente.email.lower().encode()).hexdigest()
        mailchimp_client.lists.update_list_member_tags(MAILCHIMP_LIST_ID, email_hash, {
            "tags": [{"name": "DOWNLOAD_CATALOGO", "status": "active"}]
        })
    except Exception as e:
        print(f"Errore Tag Mailchimp: {e}")
    db.session.add(nuova_nota)
    db.session.commit()
    return redirect("https://drive.google.com/file/d/1zrBVAUPpNzTNMq8d7yaYrk-4MlKyN72L/view?usp=sharing")


# ─────────────────────────────────────────────────────────────────
# UTILITY
# ─────────────────────────────────────────────────────────────────

def invia_a_produzione(ordine_data):
    try:
        response = requests.post("http://localhost:5001/api/nuovo_ordine_crm", json=ordine_data, timeout=5)
        return response.status_code == 201
    except Exception as e:
        print(f"Errore invio produzione: {e}")
        return False


def run_flask():
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)



# ─────────────────────────────────────────────────────────────────
# AVVIO APPLICAZIONE
# ─────────────────────────────────────────────────────────────────

# ─────────────────────────────────────────────────────────────────
# INIZIALIZZAZIONE DB — eseguita all'avvio (Railway + locale)
# ─────────────────────────────────────────────────────────────────
with app.app_context():
    db.create_all()
    # Auto-patch leggero: aggiunge le colonne nuove alle tabelle già esistenti
    # (db.create_all() crea solo le tabelle mancanti, non altera quelle
    # presenti). Idempotente: se la colonna c'è già non fa nulla.
    try:
        motore = db.engine.name  # 'postgresql' in produzione, 'sqlite' in locale
        colonne_da_aggiungere = [
            ('cliente', 'frequenza_visita', 'VARCHAR(20)'),
            ('cliente', 'data_ultima_visita', 'TIMESTAMP'),
        ]
        for tabella, colonna, tipo_sql in colonne_da_aggiungere:
            if motore == 'postgresql':
                db.session.execute(text(
                    f'ALTER TABLE {tabella} ADD COLUMN IF NOT EXISTS {colonna} {tipo_sql}'
                ))
            else:
                esistenti = [r[1] for r in db.session.execute(text(f'PRAGMA table_info({tabella})'))]
                if colonna not in esistenti:
                    db.session.execute(text(f'ALTER TABLE {tabella} ADD COLUMN {colonna} {tipo_sql}'))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        print(f"⚠️ Auto-patch colonne saltato: {e}")
    print("✅ Database PostgreSQL inizializzato (tabelle verificate)")


# ─────────────────────────────────────────────────────────────────
# API LEAD DAL SITO WEB (mauriziogustinicchiconsulting.it)
# Il sito Flask invia in POST JSON ogni compilazione del form contatti.
# Protetta da API key (header X-API-Key = env SITE_LEAD_API_KEY).
# ─────────────────────────────────────────────────────────────────
SITE_LEAD_API_KEY = os.environ.get('SITE_LEAD_API_KEY', '')


@app.route('/api/lead-sito', methods=['POST'])
def api_lead_sito():
    # 1. Autenticazione: nessuna sessione, solo API key condivisa
    if not SITE_LEAD_API_KEY or request.headers.get('X-API-Key') != SITE_LEAD_API_KEY:
        return jsonify({'ok': False, 'errore': 'API key mancante o non valida'}), 401

    dati = request.get_json(silent=True) or {}
    nome_persona = (dati.get('nome') or '').strip()
    email        = (dati.get('email') or '').strip().lower()
    azienda      = (dati.get('azienda') or '').strip()
    telefono     = (dati.get('telefono') or '').strip()
    messaggio    = (dati.get('messaggio') or '').strip()

    if not email or not (nome_persona or azienda):
        return jsonify({'ok': False, 'errore': 'Campi minimi: email + nome o azienda'}), 400

    try:
        # 2. Dedup su email: se il cliente esiste già non lo duplico,
        #    aggiungo solo la nota con il nuovo messaggio
        cliente = Cliente.query.filter(func.lower(Cliente.email) == email).first()
        nuovo = cliente is None

        if nuovo:
            cliente = Cliente(
                nome               = (azienda or nome_persona).upper(),
                email              = email,
                telefono           = telefono,
                referente_acquisti = nome_persona,
                tipo_anagrafica    = 'Lead',
                provincia          = None,
                data_prossimo_contatto = datetime.utcnow(),  # appare subito nei promemoria
            )
            db.session.add(cliente)
            db.session.flush()  # ottiene cliente.id prima del commit
        else:
            # aggiorna eventuali campi vuoti con i nuovi dati
            if not cliente.telefono and telefono:
                cliente.telefono = telefono
            if not cliente.referente_acquisti and nome_persona:
                cliente.referente_acquisti = nome_persona

        # 3. Nota colorata con il messaggio del form (arancio = dal sito)
        db.session.add(NotaColorata(
            cliente_id    = cliente.id,
            testo         = f"📩 LEAD DAL SITO WEB\n{messaggio}" if messaggio else "📩 LEAD DAL SITO WEB (nessun messaggio)",
            tipo_contatto = 'Sito Web',
            colore        = '#ff9900',
        ))

        # 4. Task di follow-up a 2 giorni
        db.session.add(Task(
            cliente_id    = cliente.id,
            descrizione   = f"📩 Rispondere al lead dal sito: {nome_persona or azienda}",
            data_scadenza = datetime.utcnow() + timedelta(days=2),
        ))

        db.session.commit()
        return jsonify({'ok': True, 'cliente_id': cliente.id,
                        'nuovo_cliente': nuovo}), 201 if nuovo else 200

    except Exception as e:
        db.session.rollback()
        print(f"❌ /api/lead-sito errore: {e}")
        return jsonify({'ok': False, 'errore': str(e)}), 500


if __name__ == '__main__':
    # Avvio locale — rilevamento automatico Railway vs desktop
    IS_RAILWAY = os.environ.get('RAILWAY_ENVIRONMENT') is not None

    if IS_RAILWAY:
        # Su Railway viene avviato da Gunicorn — questo blocco non viene eseguito
        app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=False)
    else:
        # Avvio locale con webview (desktop app)
        try:
            import webview
            flask_thread        = Thread(target=run_flask)
            flask_thread.daemon = True
            flask_thread.start()
            time.sleep(1)
            window = webview.create_window(
                f'{AZIENDA_NOME} CRM — Gestione Aziendale',
                'http://127.0.0.1:5000',
                width=1300, height=850,
                resizable=True, confirm_close=True
            )
            webview.start()
        except ImportError:
            # Fallback se pywebview non è installato (Railway, CI, ecc.)
            print("ℹ️  pywebview non disponibile — avvio Flask standard")
            app.run(host='0.0.0.0', port=5000, debug=True, use_reloader=False)
