# -*- coding: utf-8 -*-
"""
MAURIZIO GUSTINICCHI CONSULTING - Sito dinamico
Flask + PostgreSQL (Railway) | Blog gestito da DB | Form contatti -> CRM
"""
import os
import json
import smtplib
import threading
import re
import hmac
import hashlib
import uuid
import unicodedata
from datetime import datetime, date, timedelta
from urllib.parse import urljoin, urlparse

import bleach
from bleach.css_sanitizer import CSSSanitizer
from sqlalchemy import inspect, text
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from functools import wraps

import requests
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, abort, Response, jsonify)
from models import db, Articolo, LandingPage, Lead, Prodotto, Ordine

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mgc-dev-key-cambiami')
app.config['MAX_CONTENT_LENGTH'] = 600 * 1024

# --- Database: PostgreSQL su Railway, SQLite in locale ---
db_url = os.environ.get('DATABASE_URL', 'sqlite:///mgc_sito.db')
if db_url.startswith('postgres://'):
    db_url = db_url.replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = db_url
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db.init_app(app)

# --- Configurazione integrazione CRM ---
CRM_WEBHOOK_URL = os.environ.get('CRM_WEBHOOK_URL', '')       # endpoint del CRM che riceve i lead
CRM_API_KEY = os.environ.get('CRM_API_KEY', '')               # opzionale: header X-API-Key
LANDING_PUBLISH_API_KEY = os.environ.get('LANDING_PUBLISH_API_KEY', '')
# Chiave separata dall'integrazione landing: senza chiave l'endpoint articoli
# resta deliberatamente inaccessibile.
app.config['WEBSITE_ARTICLE_PUBLISH_API_KEY'] = os.environ.get('WEBSITE_ARTICLE_PUBLISH_API_KEY', '')

# --- Configurazione notifiche email per nuovi lead ---
SMTP_SERVER = os.environ.get('SMTP_SERVER', '')
SMTP_PORT = int(os.environ.get('SMTP_PORT', '587'))
SMTP_USER = os.environ.get('SMTP_USER', '')
SMTP_PASSWORD = os.environ.get('SMTP_PASSWORD', '')
SENDER_EMAIL = os.environ.get('SENDER_EMAIL', SMTP_USER)
NOTIFICA_EMAIL_DESTINATARIO = os.environ.get('NOTIFICA_EMAIL_DESTINATARIO',
                                              'info@mauriziogustinicchiconsulting.it')

# --- Stripe (vendita diretta) ---
# Se STRIPE_SECRET_KEY non è impostata, lo shop funziona in modalità BONIFICO:
# l'ordine viene raccolto e il cliente riceve le istruzioni per il pagamento.
STRIPE_SECRET_KEY = os.environ.get('STRIPE_SECRET_KEY', '')
STRIPE_WEBHOOK_SECRET = os.environ.get('STRIPE_WEBHOOK_SECRET', '')
IBAN_BONIFICO = os.environ.get('IBAN_BONIFICO', 'IT00 X000 0000 0000 0000 0000 000')
INTESTATARIO_BONIFICO = os.environ.get('INTESTATARIO_BONIFICO', 'Maurizio Gustinicchi')
if STRIPE_SECRET_KEY:
    import stripe
    stripe.api_key = STRIPE_SECRET_KEY

# --- Admin ---
ADMIN_USER = os.environ.get('ADMIN_USER', 'maurizio')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Mgc@Admin2026!')
IS_PRODUCTION = bool(os.environ.get('RAILWAY_ENVIRONMENT') or os.environ.get('RAILWAY_PROJECT_ID'))
ADMIN_SECURITY_CONFIGURED = bool(
    os.environ.get('SECRET_KEY') and os.environ.get('SECRET_KEY') != 'mgc-dev-key-cambiami' and
    os.environ.get('ADMIN_PASSWORD') and os.environ.get('ADMIN_PASSWORD') != 'Mgc@Admin2026!'
)

SITE_URL = os.environ.get('SITE_URL', 'https://www.mauriziogustinicchiconsulting.it')
GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY', '')
ARTICLE_TEXT_MODEL = os.environ.get('ARTICLE_TEXT_MODEL', 'gemini-2.5-flash')
ARTICLE_IMAGE_MODEL = os.environ.get('ARTICLE_IMAGE_MODEL', 'imagen-3.0-generate-002')
ARTICLE_AUTHOR = os.environ.get('ARTICLE_AUTHOR', 'Maurizio Gustinicchi')
MAX_GENERATED_IMAGE_BYTES = 10 * 1024 * 1024


def absolute_cover_url(cover):
    """Return a canonical HTTPS URL for a local or remote article cover."""
    if not cover:
        return ''
    if cover.startswith('https://'):
        return cover
    return urljoin(SITE_URL.rstrip('/') + '/', cover.lstrip('/'))


def admin_csrf_token():
    if '_admin_csrf_token' not in session:
        session['_admin_csrf_token'] = uuid.uuid4().hex
    return session['_admin_csrf_token']


def admin_csrf_valid(value=None):
    expected = session.get('_admin_csrf_token', '')
    supplied = value if value is not None else request.form.get('_csrf_token', '')
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


@app.before_request
def protect_admin_posts_from_csrf():
    """Un solo controllo coerente per tutte le azioni amministrative."""
    if request.method == 'POST' and request.path.startswith('/admin'):
        supplied = request.headers.get('X-CSRF-Token') or request.form.get('_csrf_token', '')
        if not admin_csrf_valid(supplied):
            abort(400, 'Richiesta non valida (CSRF).')


@app.context_processor
def inject_globals():
    return {
        'current_year': datetime.now().year,
        'article_cover_url': absolute_cover_url,
        'admin_csrf_token': admin_csrf_token,
    }


# =====================================================================
# PAGINE STATICHE (template convertiti dal sito Aruba)
# =====================================================================
PAGINE = ['chi-siamo', 'certificati', 'servizi', 'shop', 'formazione',
          'video', 'libri', 'partner', 'testimonianze', 'privacy-policy']

SERVIZI_DETTAGLIO = ['controllo', 'digitalizzazione', 'innovation-manager',
                     'business-reporting', 'organizzazione', 'dashboard-bi',
                     'manutenzione', 'content-factory']


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/<pagina>')
def pagina_statica(pagina):
    if pagina == 'blog':
        return redirect(url_for('blog'))
    if pagina == 'contatti':
        return redirect(url_for('contatti'))
    if pagina not in PAGINE:
        abort(404)
    return render_template(f'{pagina}.html')


@app.route('/servizi/<slug>')
def servizio_dettaglio(slug):
    if slug not in SERVIZI_DETTAGLIO:
        abort(404)
    return render_template(f'servizi/{slug}.html')


# =====================================================================
# BLOG DINAMICO (articoli su PostgreSQL, gestione da pannello admin)
# =====================================================================
@app.route('/blog')
def blog():
    articoli = (Articolo.query
                .filter_by(pubblicato=True)
                .filter(Articolo.data_pubblicazione <= date.today())
                .order_by(Articolo.data_pubblicazione.desc())
                .all())
    return render_template('blog_lista.html', articoli=articoli)


@app.route('/blog/<slug>')
def blog_articolo(slug):
    articolo = (Articolo.query.filter_by(slug=slug, pubblicato=True)
                .filter(Articolo.data_pubblicazione <= date.today()).first_or_404())
    return render_template('blog_articolo.html', a=articolo)


# =====================================================================
# CONTENT FACTORY: pubblicazione articoli dal CRM
# =====================================================================
ARTICLE_HTML_TAGS = [
    'a', 'article', 'aside', 'blockquote', 'br', 'code', 'div', 'em', 'figcaption',
    'figure', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'img', 'li', 'ol', 'p',
    'pre', 'section', 'small', 'span', 'strong', 'sub', 'sup', 'table', 'tbody',
    'td', 'th', 'thead', 'tr', 'u', 'ul'
]
ARTICLE_HTML_ATTRIBUTES = {
    '*': ['class', 'id', 'style', 'title'],
    'a': ['href', 'rel', 'target'],
    'img': ['alt', 'height', 'loading', 'src', 'width'],
    'td': ['colspan', 'rowspan'],
    'th': ['colspan', 'rowspan', 'scope'],
}
ARTICLE_CSS_SANITIZER = CSSSanitizer(allowed_css_properties=[
    'background-color', 'border', 'border-bottom', 'border-collapse', 'border-radius',
    'color', 'display', 'font-size', 'font-style', 'font-weight', 'height', 'line-height',
    'margin', 'margin-bottom', 'margin-left', 'margin-right', 'margin-top', 'max-width',
    'padding', 'padding-bottom', 'padding-left', 'padding-right', 'padding-top', 'text-align',
    'text-decoration', 'width'
])
ARTICLE_HTML_CLEANER = bleach.Cleaner(
    tags=ARTICLE_HTML_TAGS,
    attributes=ARTICLE_HTML_ATTRIBUTES,
    protocols=['http', 'https', 'mailto'],
    strip=True,
    css_sanitizer=ARTICLE_CSS_SANITIZER,
)


def _article_api_error(message, status=400):
    return jsonify({'ok': False, 'error': message}), status


def _canonical_article_hash(data):
    """Hash the normalized persisted payload, not incidental JSON formatting."""
    canonical = json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _validated_article_payload(data, external_id):
    if not isinstance(data, dict):
        return None, 'Il payload JSON deve essere un oggetto.'
    try:
        if str(uuid.UUID(external_id)) != external_id:
            raise ValueError
    except (ValueError, AttributeError):
        return None, 'external_id non valido.'

    required = ('version', 'slug', 'title', 'meta_description', 'excerpt', 'body_html',
                'status', 'publish_date')
    if any(name not in data for name in required):
        return None, 'Payload incompleto.'
    if isinstance(data['version'], bool) or not isinstance(data['version'], int) or data['version'] < 1:
        return None, 'version deve essere un intero maggiore o uguale a 1.'
    slug = data['slug']
    if not isinstance(slug, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug) or len(slug) > 200:
        return None, 'slug deve essere canonico, minuscolo e separato da trattini.'
    string_limits = {
        'title': 300, 'meta_description': 1000, 'excerpt': 5000, 'body_html': 500000,
    }
    for field, limit in string_limits.items():
        if not isinstance(data[field], str) or not data[field].strip() or len(data[field]) > limit:
            return None, f'{field} non valido.'
    if data['status'] not in ('draft', 'published'):
        return None, 'status deve essere draft o published.'
    if not isinstance(data['publish_date'], str):
        return None, 'publish_date non valido.'
    try:
        publish_date = date.fromisoformat(data['publish_date'])
    except ValueError:
        return None, 'publish_date deve essere ISO YYYY-MM-DD.'
    if publish_date.isoformat() != data['publish_date']:
        return None, 'publish_date deve essere ISO YYYY-MM-DD.'

    cover = data.get('cover', '')
    if cover is None:
        cover = ''
    if not isinstance(cover, str) or len(cover) > 400:
        return None, 'cover non valida.'
    cover = cover.strip()
    if cover:
        parsed = urlparse(cover)
        is_https_url = parsed.scheme == 'https' and bool(parsed.hostname)
        # Both /static/x.jpg and static/x.jpg are paths; rendering normalizes
        # either form to an absolute SITE_URL-based URL.
        is_safe_path = (not parsed.scheme and not parsed.netloc and not cover.startswith('//') and
                        '\\' not in cover and '..' not in cover.split('/'))
        if not (is_https_url or is_safe_path):
            return None, 'cover deve essere un path o un URL HTTPS.'

    normalized = {
        'version': data['version'], 'slug': slug, 'title': data['title'].strip(),
        'meta_description': data['meta_description'].strip(), 'excerpt': data['excerpt'].strip(),
        'body_html': ARTICLE_HTML_CLEANER.clean(data['body_html']), 'status': data['status'],
        'publish_date': publish_date.isoformat(), 'cover': cover.strip(),
    }
    if not normalized['body_html'].strip():
        return None, 'body_html non contiene HTML consentito.'
    return normalized, None


@app.route('/api/internal/articles/<external_id>', methods=['PUT'])
def api_publish_article(external_id):
    api_key = app.config.get('WEBSITE_ARTICLE_PUBLISH_API_KEY', '')
    supplied_key = request.headers.get('X-API-Key', '')
    if not api_key or not hmac.compare_digest(supplied_key, api_key):
        return _article_api_error('Chiave API non valida.', 401)
    data = request.get_json(silent=True)
    if data is None:
        return _article_api_error('JSON non valido.')
    payload, error = _validated_article_payload(data, external_id)
    if error:
        return _article_api_error(error)

    payload_hash = _canonical_article_hash(payload)
    article = Articolo.query.filter_by(external_id=external_id).first()
    incoming_version = payload['version']
    if article:
        if incoming_version < article.version:
            return _article_api_error('Versione precedente a quella pubblicata.', 409)
        if incoming_version == article.version:
            if hmac.compare_digest(article.payload_hash or '', payload_hash):
                return jsonify({'ok': True, 'id': article.id, 'version': article.version,
                                'url': f'{SITE_URL.rstrip("/")}/blog/{article.slug}',
                                'status': 'published' if article.pubblicato else 'draft'}), 200
            return _article_api_error('Stessa versione con payload differente.', 409)

    slug_owner = Articolo.query.filter_by(slug=payload['slug']).first()
    if slug_owner and slug_owner.external_id != external_id:
        return _article_api_error('Slug già utilizzato da un altro articolo.', 409)
    created = article is None
    if created:
        article = Articolo(external_id=external_id)
        db.session.add(article)
    article.version = incoming_version
    article.slug = payload['slug']
    article.titolo = payload['title']
    article.meta_description = payload['meta_description']
    article.excerpt = payload['excerpt']
    article.body = payload['body_html']
    article.cover = payload['cover']
    article.data_pubblicazione = date.fromisoformat(payload['publish_date'])
    article.pubblicato = payload['status'] == 'published'
    article.stato = 'pubblicato' if article.pubblicato else 'bozza'
    if article.pubblicato and not article.published_at:
        article.published_at = datetime.utcnow()
    elif not article.pubblicato:
        article.published_at = None
    article.autore = article.autore or ARTICLE_AUTHOR
    article.payload_hash = payload_hash
    db.session.commit()
    return jsonify({'ok': True, 'id': article.id, 'version': article.version,
                    'url': f'{SITE_URL.rstrip("/")}/blog/{article.slug}',
                    'status': payload['status']}), 201 if created else 200


# =====================================================================
# CONTATTI: salva lead su DB + invio al CRM via webhook
# =====================================================================
def invia_email_notifica_lead(lead_dict):
    """Invia una email di notifica a info@mauriziogustinicchiconsulting.it
    ogni volta che arriva un nuovo lead dal form contatti. Configurabile
    tramite le variabili d'ambiente SMTP_SERVER, SMTP_PORT, SMTP_USER,
    SMTP_PASSWORD, SENDER_EMAIL. Se SMTP non è configurato, non fa nulla
    (il lead resta comunque salvato nel DB)."""
    if not SMTP_SERVER or not SMTP_USER or not SMTP_PASSWORD:
        print('Notifica email non inviata: SMTP non configurato (SMTP_SERVER/SMTP_USER/SMTP_PASSWORD).')
        return
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = f"Nuovo lead dal sito: {lead_dict.get('nome', '')}"
        msg['From'] = SENDER_EMAIL
        msg['To'] = NOTIFICA_EMAIL_DESTINATARIO

        testo = (
            f"Nuovo lead ricevuto dal form contatti del sito:\n\n"
            f"Nome: {lead_dict.get('nome', '')}\n"
            f"Email: {lead_dict.get('email', '')}\n"
            f"Azienda: {lead_dict.get('azienda', '')}\n"
            f"Telefono: {lead_dict.get('telefono', '')}\n"
            f"Messaggio: {lead_dict.get('messaggio', '')}\n"
            f"Data: {lead_dict.get('data', '')}\n\n"
            f"Vai al pannello admin: {SITE_URL}/admin\n"
        )

        html = f"""
        <html>
          <body style="font-family:Arial, sans-serif; color:#222;">
            <h2 style="color:#004d99;">📩 Nuovo lead dal sito web</h2>
            <table style="border-collapse:collapse;">
              <tr><td style="padding:6px; font-weight:bold;">Nome</td><td style="padding:6px;">{lead_dict.get('nome', '')}</td></tr>
              <tr><td style="padding:6px; font-weight:bold;">Email</td><td style="padding:6px;">{lead_dict.get('email', '')}</td></tr>
              <tr><td style="padding:6px; font-weight:bold;">Azienda</td><td style="padding:6px;">{lead_dict.get('azienda', '')}</td></tr>
              <tr><td style="padding:6px; font-weight:bold;">Telefono</td><td style="padding:6px;">{lead_dict.get('telefono', '')}</td></tr>
              <tr><td style="padding:6px; font-weight:bold;">Messaggio</td><td style="padding:6px;">{lead_dict.get('messaggio', '')}</td></tr>
              <tr><td style="padding:6px; font-weight:bold;">Data</td><td style="padding:6px;">{lead_dict.get('data', '')}</td></tr>
            </table>
            <p style="margin-top:20px;">
              <a href="{SITE_URL}/admin" style="background:#004d99; color:white; padding:10px 18px; border-radius:4px; text-decoration:none;">Apri pannello admin</a>
            </p>
          </body>
        </html>
        """

        msg.attach(MIMEText(testo, 'plain'))
        msg.attach(MIMEText(html, 'html'))

        with smtplib.SMTP(SMTP_SERVER, SMTP_PORT, timeout=15) as server:
            server.starttls()
            server.login(SMTP_USER, SMTP_PASSWORD)
            server.sendmail(SENDER_EMAIL, [NOTIFICA_EMAIL_DESTINATARIO], msg.as_string())
    except Exception as e:
        print(f'Errore invio email notifica lead: {e}')


def invia_lead_al_crm(lead_dict):
    """Invio asincrono del lead al CRM. Il lead resta comunque nel DB del sito
    come backup: se il CRM non risponde, non si perde nulla."""
    if not CRM_WEBHOOK_URL:
        return
    headers = {'Content-Type': 'application/json'}
    if CRM_API_KEY:
        headers['X-API-Key'] = CRM_API_KEY
    try:
        r = requests.post(CRM_WEBHOOK_URL, json=lead_dict, headers=headers, timeout=10)
        # marca il lead come sincronizzato
        with app.app_context():
            lead = Lead.query.get(lead_dict['_lead_id'])
            if lead:
                lead.sincronizzato_crm = (r.status_code in (200, 201))
                lead.risposta_crm = f'{r.status_code}: {r.text[:300]}'
                db.session.commit()
    except Exception as e:
        with app.app_context():
            lead = Lead.query.get(lead_dict['_lead_id'])
            if lead:
                lead.risposta_crm = f'ERRORE: {e}'
                db.session.commit()


@app.route('/contatti', methods=['GET', 'POST'])
def contatti():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        email = request.form.get('email', '').strip()
        azienda = request.form.get('azienda', '').strip()
        telefono = request.form.get('telefono', '').strip()
        messaggio = request.form.get('messaggio', '').strip()

        if not nome or not email or not messaggio:
            flash('Compila tutti i campi obbligatori (nome, email, messaggio).', 'error')
            return redirect(url_for('contatti'))

        lead = Lead(nome=nome, email=email, azienda=azienda,
                    telefono=telefono, messaggio=messaggio,
                    fonte='sito_web', pagina_origine=request.referrer or '/contatti')
        db.session.add(lead)
        db.session.commit()

        payload = {
            '_lead_id': lead.id,
            'nome': nome,
            'email': email,
            'azienda': azienda,
            'telefono': telefono,
            'messaggio': messaggio,
            'fonte': 'Sito Web - mauriziogustinicchiconsulting.it',
            'data': datetime.now().isoformat(),
        }
        threading.Thread(target=invia_lead_al_crm, args=(payload,), daemon=True).start()
        threading.Thread(target=invia_email_notifica_lead, args=(payload,), daemon=True).start()

        flash('Messaggio inviato con successo! Ti risponderò al più presto.', 'success')
        return redirect(url_for('contatti'))

    return render_template('contatti.html')



# =====================================================================
# LANDING PAGE: pubblicazione dalla Content Factory + raccolta lead
# =====================================================================
def _validate_landing_payload(data):
    required = ('id', 'version', 'slug', 'status', 'title', 'blocks')
    if any(key not in data for key in required):
        return 'Payload incompleto.'
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', str(data.get('id', ''))):
        return 'ID landing non valido.'
    if not re.fullmatch(r'[a-z0-9-]{1,160}', str(data.get('slug', ''))):
        return 'Slug non valido.'
    if data.get('status') not in ('published', 'draft', 'archived'):
        return 'Stato non valido.'
    if not isinstance(data.get('blocks'), list) or len(data['blocks']) > 12:
        return 'Blocchi non validi.'
    allowed = {'hero', 'benefits', 'lead_form'}
    if any(not isinstance(b, dict) or b.get('type') not in allowed or not isinstance(b.get('props', {}), dict) for b in data['blocks']):
        return 'Tipo di blocco non consentito.'
    theme = data.get('theme') or {}
    for color in (theme.get('primary', '#0d2b4e'), theme.get('accent', '#e05252')):
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', str(color)):
            return 'Colore non valido.'
    try:
        version = int(data.get('version'))
        if version < 1:
            return 'Versione non valida.'
    except (TypeError, ValueError):
        return 'Versione non valida.'
    return None


@app.route('/api/internal/landing-pages/<external_id>', methods=['PUT'])
def api_publish_landing(external_id):
    if not LANDING_PUBLISH_API_KEY or request.headers.get('X-API-Key', '') != LANDING_PUBLISH_API_KEY:
        return jsonify({'status': 'error', 'message': 'Chiave API non valida'}), 401
    data = request.get_json(silent=True) or {}
    if data.get('id') != external_id:
        return jsonify({'status': 'error', 'message': 'ID non coerente'}), 400
    error = _validate_landing_payload(data)
    if error:
        return jsonify({'status': 'error', 'message': error}), 400
    page = LandingPage.query.filter_by(external_id=external_id).first()
    incoming_version = int(data['version'])
    if page and incoming_version < page.version:
        return jsonify({'status': 'error', 'message': 'Versione precedente a quella pubblicata'}), 409
    slug_owner = LandingPage.query.filter_by(slug=data['slug']).first()
    if slug_owner and slug_owner.external_id != external_id:
        return jsonify({'status': 'error', 'message': 'Slug già utilizzato'}), 409
    if page is None:
        page = LandingPage(external_id=external_id)
        db.session.add(page)
    page.version = incoming_version
    page.slug = data['slug']
    page.status = data['status']
    page.title = str(data['title'])[:200]
    page.meta_description = str((data.get('seo') or {}).get('description', ''))[:300]
    page.payload_json = json.dumps(data, ensure_ascii=False)
    db.session.commit()
    public_url = f"{SITE_URL}/landing/{page.slug}"
    return jsonify({'status': 'success', 'id': external_id, 'version': page.version,
                    'public_url': public_url}), 201 if incoming_version == 1 else 200


def _landing_block(payload, block_type):
    return next((b.get('props', {}) for b in payload.get('blocks', []) if b.get('type') == block_type), {})


@app.route('/landing/<slug>', methods=['GET', 'POST'])
def landing_pubblica(slug):
    page = LandingPage.query.filter_by(slug=slug, status='published').first_or_404()
    payload = page.payload
    if request.method == 'POST':
        # Honeypot: i browser umani non compilano questo campo nascosto.
        if request.form.get('website', '').strip():
            return redirect(url_for('landing_pubblica', slug=slug))
        nome = request.form.get('nome', '').strip()[:200]
        email = request.form.get('email', '').strip()[:200]
        azienda = request.form.get('azienda', '').strip()[:200]
        telefono = request.form.get('telefono', '').strip()[:50]
        messaggio = request.form.get('messaggio', '').strip()[:5000]
        privacy = request.form.get('privacy') == 'on'
        if not nome or not email or '@' not in email or not privacy:
            flash('Inserisci nome, email valida e accetta la privacy policy.', 'error')
            return render_template('landing_page.html', page=page, data=payload,
                                   hero=_landing_block(payload, 'hero'),
                                   benefits=_landing_block(payload, 'benefits'),
                                   form_block=_landing_block(payload, 'lead_form'))
        utm = {key: request.form.get(key, '').strip()[:200]
               for key in ('utm_source', 'utm_medium', 'utm_campaign', 'utm_content', 'utm_term')}
        source = (payload.get('lead_config') or {}).get('source') or f'landing:{slug}'
        lead = Lead(nome=nome, email=email, azienda=azienda, telefono=telefono,
                    messaggio=messaggio or f'Richiesta dalla landing {page.title}',
                    fonte=source[:100], pagina_origine=f'/landing/{slug}')
        db.session.add(lead)
        db.session.commit()
        lead_payload = {
            '_lead_id': lead.id, 'event_id': f'landing-{page.external_id}-{lead.id}',
            'nome': nome, 'email': email, 'azienda': azienda, 'telefono': telefono,
            'messaggio': lead.messaggio, 'fonte': source,
            'landing_id': page.external_id, 'landing_slug': slug,
            'landing_version': page.version, 'pagina_origine': f'/landing/{slug}',
            'utm': utm, 'consenso_privacy': True, 'data': datetime.now().isoformat(),
        }
        threading.Thread(target=invia_lead_al_crm, args=(lead_payload,), daemon=True).start()
        threading.Thread(target=invia_email_notifica_lead, args=(lead_payload,), daemon=True).start()
        return redirect(url_for('landing_pubblica', slug=slug, inviato='1'))
    return render_template('landing_page.html', page=page, data=payload,
                           hero=_landing_block(payload, 'hero'),
                           benefits=_landing_block(payload, 'benefits'),
                           form_block=_landing_block(payload, 'lead_form'))



# =====================================================================
# AGENTE AI (sostituisce l'app Streamlit esterna: gira qui su Railway,
# non dorme mai e legge i contenuti del sito direttamente dal DB)
# =====================================================================
from agente import chiedi_agente


@app.route('/api/agente', methods=['POST'])
def api_agente():
    dati = request.get_json(silent=True) or {}
    messaggio = (dati.get('messaggio') or '').strip()
    if not messaggio:
        return {'risposta': 'Scrivi una domanda!'}, 400
    storia = dati.get('storia') or []
    risposta = chiedi_agente(messaggio, storia)
    return {'risposta': risposta}


# =====================================================================
# SEO: redirect 301 dai vecchi URL .html (indicizzati su Google)
# =====================================================================
@app.route('/index.html')
def r_index():
    return redirect('/', code=301)


@app.route('/<pagina>.html')
def r_html(pagina):
    return redirect(f'/{pagina}', code=301)


@app.route('/servizi/dettaglio-<slug>.html')
def r_servizio(slug):
    return redirect(f'/servizi/{slug}', code=301)


@app.route('/blog/articolo-<path:slug>.html')
def r_blog(slug):
    return redirect(f'/blog/{slug}', code=301)


# =====================================================================
# SITEMAP + ROBOTS
# =====================================================================
@app.route('/sitemap.xml')
def sitemap():
    urls = [f'{SITE_URL}/'] + [f'{SITE_URL}/{p}' for p in PAGINE]
    urls += [f'{SITE_URL}/servizi/{s}' for s in SERVIZI_DETTAGLIO]
    urls += [f'{SITE_URL}/blog', f'{SITE_URL}/contatti', f'{SITE_URL}/negozio']
    for a in (Articolo.query.filter_by(pubblicato=True)
              .filter(Articolo.data_pubblicazione <= date.today()).all()):
        urls.append(f'{SITE_URL}/blog/{a.slug}')
    for landing in LandingPage.query.filter_by(status='published').all():
        urls.append(f'{SITE_URL}/landing/{landing.slug}')
    xml = ['<?xml version="1.0" encoding="UTF-8"?>',
           '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for u in urls:
        xml.append(f'  <url><loc>{u}</loc></url>')
    xml.append('</urlset>')
    return Response('\n'.join(xml), mimetype='application/xml')


@app.route('/robots.txt')
def robots():
    return Response(f'User-agent: *\nAllow: /\nDisallow: /admin\nSitemap: {SITE_URL}/sitemap.xml',
                    mimetype='text/plain')


# =====================================================================
# ASSISTENTE IA ARTICOLI (testo + copertina persistente)
# =====================================================================
PLACEHOLDER_PATTERNS = (
    (re.compile(r'\[(?:inserire|nome|data|azienda|testo|placeholder|da completare)[^\]]*\]', re.I),
     'placeholder tra parentesi quadre'),
    (re.compile(r'\b(?:lorem ipsum|todo|tbd|da completare|testo segnaposto)\b', re.I),
     'testo provvisorio'),
    (re.compile(r'\{\{[^}]+\}\}|\$\{[^}]+\}', re.I), 'variabile non compilata'),
)


def validate_admin_cover(value):
    cover = (value or '').strip()
    if not cover:
        return ''
    parsed = urlparse(cover)
    is_https = parsed.scheme == 'https' and bool(parsed.hostname)
    is_safe_path = (not parsed.scheme and not parsed.netloc and not cover.startswith('//') and
                    '\\' not in cover and '..' not in cover.split('/'))
    if not (is_https or is_safe_path):
        raise ValueError('La copertina deve essere un path del sito o un URL HTTPS sicuro.')
    return cover


def sanitize_article_styles(value):
    raw = (value or '').strip()
    if not raw:
        return ''
    raw = re.sub(r'^\s*<style(?:\s[^>]*)?>', '', raw, flags=re.I)
    raw = re.sub(r'</style>\s*$', '', raw, flags=re.I)
    if '<' in raw or '>' in raw or re.search(r'@import|expression\s*\(|javascript\s*:|data\s*:', raw, re.I):
        raise ValueError('Il CSS contiene markup o istruzioni non consentite.')
    return f'<style>{raw}</style>'


def slugify_article(value):
    normalized = unicodedata.normalize('NFKD', value or '').encode('ascii', 'ignore').decode('ascii')
    return re.sub(r'-+', '-', re.sub(r'[^a-z0-9]+', '-', normalized.lower())).strip('-')[:180]


def unique_article_slug(value, article_id=None):
    base = slugify_article(value) or f'articolo-{date.today().isoformat()}'
    candidate, suffix = base, 2
    while True:
        owner = Articolo.query.filter_by(slug=candidate).first()
        if not owner or owner.id == article_id:
            return candidate
        candidate = f'{base[:170]}-{suffix}'
        suffix += 1


def article_placeholder_issues(*values):
    text_value = '\n'.join(str(value or '') for value in values)
    return sorted({label for pattern, label in PLACEHOLDER_PATTERNS if pattern.search(text_value)})


def _google_ai_client():
    if not GOOGLE_API_KEY:
        raise RuntimeError('GOOGLE_API_KEY non configurata sul servizio Railway del sito.')
    from google import genai
    return genai.Client(api_key=GOOGLE_API_KEY)


def generate_article_draft_ai(titolo, pubblico, tono, traccia):
    """Genera un articolo strutturato in JSON; nessun contenuto viene pubblicato."""
    from google.genai import types as genai_types
    prompt = f'''Sei un autore e consulente SEO italiano esperto di PMI, controllo di gestione,
organizzazione e trasformazione digitale. Scrivi un articolo autorevole, concreto e approfondito.

INPUT VINCOLANTE
Titolo provvisorio: {titolo}
Pubblico: {pubblico}
Tono di voce: {tono}
Concetti da sviluppare:
{traccia}

REGOLE NON NEGOZIABILI
- Sviluppa tutti e soltanto i concetti forniti, collegandoli in modo logico.
- Non inventare dati, percentuali, clienti, casi, citazioni, normative o fonti.
- Vietati cliché sull'IA, frasi generiche, promesse miracolose e ripetizioni.
- Vietati placeholder, parentesi da compilare, TODO, testo troncato o frasi lasciate a metà.
- Apri con <article> e un <header> contenente un solo H1 coerente con il titolo.
- Produci HTML semantico pulito con paragrafi, H2/H3, elenchi e una conclusione operativa.
- Lunghezza indicativa: 1.200-1.800 parole, in italiano corretto.
- Nessun Markdown e nessun blocco ```.

Rispondi soltanto con un oggetto JSON valido con ESATTAMENTE queste chiavi:
"title", "meta_description", "excerpt", "body_html", "image_prompt".
La meta_description deve essere concreta e lunga massimo 160 caratteri.
L'excerpt deve essere di 2-3 frasi.
L'image_prompt deve descrivere una copertina orizzontale 16:9 elegante, fotorealistica o editoriale,
senza testo, lettere, loghi, marchi o persone riconoscibili, coerente con l'articolo.'''
    response = _google_ai_client().models.generate_content(
        model=ARTICLE_TEXT_MODEL,
        contents=prompt,
        config=genai_types.GenerateContentConfig(response_mime_type='application/json')
    )
    raw = (response.text or '').strip()
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f'La risposta IA non è JSON valido: {exc}') from exc
    required = ('title', 'meta_description', 'excerpt', 'body_html', 'image_prompt')
    if not isinstance(result, dict) or any(not str(result.get(key, '')).strip() for key in required):
        raise ValueError('La risposta IA è incompleta.')
    clean = {key: str(result[key]).strip() for key in required}
    clean['meta_description'] = clean['meta_description'][:160].strip()
    clean['body_html'] = ARTICLE_HTML_CLEANER.clean(clean['body_html'])
    visible_text = re.sub(r'<[^>]+>', ' ', clean['body_html'])
    if len(re.sub(r'\s+', ' ', visible_text).strip()) < 1800:
        raise ValueError('La bozza generata è troppo breve: riprova per ottenere un articolo approfondito.')
    issues = article_placeholder_issues(*clean.values())
    if issues:
        raise ValueError('Bozza bloccata dal controllo qualità: ' + ', '.join(issues) + '.')
    return clean


def generate_article_cover_ai(prompt):
    """Genera PNG 16:9 con Imagen e restituisce bytes verificati."""
    from google.genai import types as genai_types
    safe_prompt = (prompt or '').strip()
    if not safe_prompt:
        raise ValueError('Prompt immagine mancante.')
    safe_prompt += ('\nFormato orizzontale 16:9, copertina editoriale professionale. '
                    'Nessun testo, lettera, numero, logo, marchio o watermark.')
    response = _google_ai_client().models.generate_images(
        model=ARTICLE_IMAGE_MODEL,
        prompt=safe_prompt,
        config=genai_types.GenerateImagesConfig(number_of_images=1, aspect_ratio='16:9')
    )
    generated = getattr(response, 'generated_images', None) or []
    image_bytes = generated[0].image.image_bytes if generated else None
    if not image_bytes:
        raise ValueError('Il servizio immagini non ha restituito una copertina.')
    image_bytes = bytes(image_bytes)
    if len(image_bytes) > MAX_GENERATED_IMAGE_BYTES:
        raise ValueError('La copertina generata supera il limite di 10 MB.')
    return image_bytes, 'image/png'


# =====================================================================
# PANNELLO ADMIN (blog + lead)
# =====================================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if IS_PRODUCTION and not ADMIN_SECURITY_CONFIGURED:
            return Response('Area admin disattivata: configurare SECRET_KEY e ADMIN_PASSWORD su Railway.', status=503)
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapper


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if IS_PRODUCTION and not ADMIN_SECURITY_CONFIGURED:
        return Response('Area admin disattivata: configurare SECRET_KEY e ADMIN_PASSWORD su Railway.', status=503)
    if request.method == 'POST':
        if (request.form.get('username') == ADMIN_USER and
                request.form.get('password') == ADMIN_PASSWORD):
            session['admin'] = True
            return redirect(url_for('admin_dashboard'))
        flash('Credenziali non valide.', 'error')
    return render_template('admin/login.html')


@app.route('/admin/logout')
def admin_logout():
    session.pop('admin', None)
    return redirect(url_for('index'))


@app.route('/admin')
@login_required
def admin_dashboard():
    articoli = Articolo.query.order_by(Articolo.data_pubblicazione.desc()).all()
    leads = Lead.query.order_by(Lead.creato_il.desc()).limit(50).all()
    return render_template('admin/dashboard.html', articoli=articoli, leads=leads)


@app.route('/admin/articolo/nuovo', methods=['GET', 'POST'])
@app.route('/admin/articolo/<int:art_id>', methods=['GET', 'POST'])
@login_required
def admin_articolo(art_id=None):
    articolo = Articolo.query.get(art_id) if art_id else None
    if request.method == 'POST':
        if not admin_csrf_valid():
            abort(400, 'Richiesta non valida (CSRF).')
        # Dopo la generazione IA la bozza esiste già nel DB, anche se la form
        # era stata aperta da /nuovo: riutilizziamo quella riga senza duplicarla.
        draft_id = request.form.get('article_id', type=int)
        if not articolo and draft_id:
            articolo = Articolo.query.get_or_404(draft_id)
        if not articolo:
            # Valori temporanei validi: evitano violazioni NOT NULL prima che
            # la form venga validata e consolidata più sotto.
            articolo = Articolo(
                slug=f'bozza-{uuid.uuid4().hex[:12]}', titolo='Bozza in lavorazione',
                body='<p>Bozza in lavorazione</p>', pubblicato=False,
                stato='bozza', autore=ARTICLE_AUTHOR
            )
            db.session.add(articolo)

        titolo = request.form.get('titolo', '').strip()
        slug_requested = request.form.get('slug', '').strip()
        body = ARTICLE_HTML_CLEANER.clean(request.form.get('body', ''))
        pubblica = request.form.get('azione') == 'pubblica'
        if not titolo or not body.strip():
            flash('Titolo e contenuto sono obbligatori.', 'error')
            return render_template('admin/articolo_form.html', a=articolo), 400
        canonical_slug = slugify_article(slug_requested or titolo)
        if not canonical_slug:
            flash('Slug non valido.', 'error')
            return render_template('admin/articolo_form.html', a=articolo), 400
        owner = Articolo.query.filter(Articolo.slug == canonical_slug, Articolo.id != articolo.id).first()
        if owner:
            flash('Questo slug è già utilizzato da un altro articolo.', 'error')
            return render_template('admin/articolo_form.html', a=articolo), 409

        data_str = request.form.get('data_pubblicazione', '') or date.today().isoformat()
        try:
            publish_date = date.fromisoformat(data_str)
        except ValueError:
            flash('Data di pubblicazione non valida.', 'error')
            return render_template('admin/articolo_form.html', a=articolo), 400
        try:
            external_cover = validate_admin_cover(request.form.get('cover', ''))
            clean_styles = sanitize_article_styles(request.form.get('styles', ''))
        except ValueError as exc:
            flash(str(exc), 'error')
            return render_template('admin/articolo_form.html', a=articolo), 400

        if pubblica:
            issues = article_placeholder_issues(titolo, request.form.get('meta_description'),
                                                request.form.get('excerpt'), body)
            if issues:
                flash('Pubblicazione bloccata: ' + ', '.join(issues) + '.', 'error')
                return render_template('admin/articolo_form.html', a=articolo), 400
            visible_text = re.sub(r'<[^>]+>', ' ', body)
            if len(re.sub(r'\s+', ' ', visible_text).strip()) < 800:
                flash('Pubblicazione bloccata: l’articolo è troppo breve per essere approfondito.', 'error')
                return render_template('admin/articolo_form.html', a=articolo), 400
            if not (external_cover or articolo.cover_data):
                flash('Pubblicazione bloccata: genera o indica una copertina.', 'error')
                return render_template('admin/articolo_form.html', a=articolo), 400

        articolo.slug = canonical_slug
        articolo.titolo = titolo
        articolo.meta_description = request.form.get('meta_description', '').strip()[:160]
        articolo.excerpt = request.form.get('excerpt', '').strip()
        articolo.body = body
        articolo.styles = clean_styles
        articolo.traccia_input = request.form.get('traccia_input', '').strip()
        articolo.pubblico_target = request.form.get('pubblico_target', '').strip()
        articolo.tono_voce = request.form.get('tono_voce', '').strip()
        articolo.autore = request.form.get('autore', '').strip() or ARTICLE_AUTHOR
        articolo.image_prompt = request.form.get('image_prompt', '').strip()
        articolo.data_pubblicazione = publish_date
        articolo.pubblicato = pubblica
        articolo.stato = 'pubblicato' if pubblica else 'bozza'
        if pubblica and not articolo.published_at:
            articolo.published_at = datetime.utcnow()
        elif not pubblica:
            articolo.published_at = None
        if external_cover and not articolo.cover_data:
            articolo.cover = external_cover
        elif articolo.cover_data:
            articolo.cover_filename = f'{canonical_slug}.png'
            articolo.cover = url_for('article_cover_media', art_id=articolo.id,
                                     filename=articolo.cover_filename)
        db.session.commit()
        flash('✅ Articolo pubblicato online.' if pubblica else '💾 Bozza salvata.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/articolo_form.html', a=articolo, default_author=ARTICLE_AUTHOR)


@app.route('/admin/api/articoli/genera-bozza', methods=['POST'])
@login_required
def admin_genera_bozza_articolo():
    if not admin_csrf_valid(request.headers.get('X-CSRF-Token', '')):
        return jsonify({'ok': False, 'error': 'Richiesta non valida (CSRF).'}), 400
    data = request.get_json(silent=True) or {}
    titolo = str(data.get('titolo', '')).strip()
    pubblico = str(data.get('pubblico_target', '')).strip()
    tono = str(data.get('tono_voce', '')).strip()
    traccia = str(data.get('traccia_input', '')).strip()
    if not titolo or not pubblico or not tono or not traccia:
        return jsonify({'ok': False, 'error': 'Compila titolo, pubblico, tono e concetti chiave.'}), 400
    if any(len(value) > limit for value, limit in ((titolo, 300), (pubblico, 200),
                                                     (tono, 100), (traccia, 12000))):
        return jsonify({'ok': False, 'error': 'Uno dei campi supera la lunghezza consentita.'}), 400
    article_id = data.get('article_id')
    articolo = Articolo.query.get(article_id) if article_id else None
    if article_id and not articolo:
        return jsonify({'ok': False, 'error': 'Bozza non trovata.'}), 404
    try:
        generated = generate_article_draft_ai(titolo, pubblico, tono, traccia)
        if not articolo:
            articolo = Articolo(
                slug=unique_article_slug(generated['title']),
                titolo=generated['title'], body=generated['body_html'],
                pubblicato=False, stato='bozza', autore=ARTICLE_AUTHOR
            )
            db.session.add(articolo)
            db.session.flush()
        articolo.titolo = generated['title']
        articolo.slug = unique_article_slug(generated['title'], articolo.id)
        articolo.meta_description = generated['meta_description']
        articolo.excerpt = generated['excerpt']
        articolo.body = generated['body_html']
        articolo.image_prompt = generated['image_prompt']
        articolo.traccia_input = traccia
        articolo.pubblico_target = pubblico
        articolo.tono_voce = tono
        articolo.autore = articolo.autore or ARTICLE_AUTHOR
        articolo.data_pubblicazione = articolo.data_pubblicazione or date.today()
        articolo.pubblicato = False
        articolo.stato = 'bozza'
        articolo.published_at = None
        db.session.commit()
        return jsonify({
            'ok': True,
            'article_id': articolo.id,
            'title': articolo.titolo,
            'slug': articolo.slug,
            'meta_description': articolo.meta_description,
            'excerpt': articolo.excerpt,
            'body_html': articolo.body,
            'image_prompt': articolo.image_prompt,
            'cover_url': articolo.cover or '',
            'message': 'Bozza generata e archiviata nel database. Ora rileggila e modificala liberamente.'
        })
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('Generazione bozza articolo fallita')
        return jsonify({'ok': False, 'error': str(exc)}), 502


@app.route('/admin/api/articoli/<int:art_id>/genera-copertina', methods=['POST'])
@login_required
def admin_genera_copertina_articolo(art_id):
    if not admin_csrf_valid(request.headers.get('X-CSRF-Token', '')):
        return jsonify({'ok': False, 'error': 'Richiesta non valida (CSRF).'}), 400
    articolo = Articolo.query.get_or_404(art_id)
    data = request.get_json(silent=True) or {}
    image_prompt = str(data.get('image_prompt') or articolo.image_prompt or '').strip()
    if not image_prompt or len(image_prompt) > 6000:
        return jsonify({'ok': False, 'error': 'Prompt immagine mancante o troppo lungo.'}), 400
    try:
        image_bytes, mimetype = generate_article_cover_ai(image_prompt)
        articolo.image_prompt = image_prompt
        articolo.cover_data = image_bytes
        articolo.cover_mimetype = mimetype
        articolo.cover_filename = f'{articolo.slug}.png'
        articolo.cover = url_for('article_cover_media', art_id=articolo.id,
                                 filename=articolo.cover_filename)
        db.session.commit()
        return jsonify({'ok': True, 'cover_url': articolo.cover + f'?v={int(datetime.utcnow().timestamp())}',
                        'message': 'Copertina generata e archiviata in modo permanente.'})
    except Exception as exc:
        db.session.rollback()
        app.logger.exception('Generazione copertina articolo fallita')
        return jsonify({'ok': False, 'error': str(exc)}), 502


@app.route('/media/articoli/<int:art_id>/<path:filename>')
def article_cover_media(art_id, filename):
    articolo = Articolo.query.get_or_404(art_id)
    if not articolo.cover_data or filename != articolo.cover_filename:
        abort(404)
    if not articolo.pubblicato and not session.get('admin'):
        abort(404)
    etag = hashlib.sha256(articolo.cover_data).hexdigest()
    response = Response(articolo.cover_data, mimetype=articolo.cover_mimetype or 'image/png')
    response.set_etag(etag)
    response.make_conditional(request)
    if articolo.pubblicato:
        response.headers['Cache-Control'] = 'public, max-age=86400'
    else:
        response.headers['Cache-Control'] = 'private, no-store'
        response.headers['Vary'] = 'Cookie'
    response.headers['Content-Disposition'] = f'inline; filename="{articolo.cover_filename}"'
    return response


@app.route('/admin/articolo/<int:art_id>/elimina', methods=['POST'])
@login_required
def admin_articolo_elimina(art_id):
    articolo = Articolo.query.get_or_404(art_id)
    db.session.delete(articolo)
    db.session.commit()
    flash('Articolo eliminato.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/admin/lead/<int:lead_id>/reinvia', methods=['POST'])
@login_required
def admin_lead_reinvia(lead_id):
    lead = Lead.query.get_or_404(lead_id)
    payload = {'_lead_id': lead.id, 'nome': lead.nome, 'email': lead.email,
               'azienda': lead.azienda, 'telefono': lead.telefono,
               'messaggio': lead.messaggio,
               'fonte': 'Sito Web - mauriziogustinicchiconsulting.it (reinvio)',
               'data': lead.creato_il.isoformat()}
    threading.Thread(target=invia_lead_al_crm, args=(payload,), daemon=True).start()
    flash(f'Lead #{lead.id} reinviato al CRM.', 'success')
    return redirect(url_for('admin_dashboard'))


@app.route('/api/leads/check-new')
@login_required
def api_leads_check_new():
    """Usato dalla dashboard admin per il polling: restituisce i lead arrivati
    di recente e non ancora 'notificati' via desktop, poi li marca come tali.
    Il frontend chiama questo endpoint ogni 10 secondi e mostra una
    Notification() del browser per ogni nuovo lead trovato."""
    soglia = datetime.utcnow() - timedelta(minutes=30)
    nuovi = (Lead.query
             .filter(Lead.notificato_desktop.is_(False))
             .filter(Lead.creato_il >= soglia)
             .order_by(Lead.creato_il.asc())
             .all())

    risultato = [{
        'id': l.id,
        'nome': l.nome,
        'email': l.email,
        'azienda': l.azienda,
        'messaggio': l.messaggio[:150],
        'creato_il': l.creato_il.strftime('%d/%m/%Y %H:%M'),
    } for l in nuovi]

    for l in nuovi:
        l.notificato_desktop = True
    if nuovi:
        db.session.commit()

    return jsonify({'nuovi_lead': risultato})


# =====================================================================
# NEGOZIO: vendita diretta libri e software
# =====================================================================
def invia_ordine_al_crm(ordine_id):
    """Il cliente che acquista finisce nel CRM come lead/cliente."""
    if not CRM_WEBHOOK_URL:
        return
    with app.app_context():
        o = Ordine.query.get(ordine_id)
        if not o:
            return
        payload = {
            '_lead_id': 0,
            'nome': o.nome,
            'email': o.email,
            'azienda': '',
            'telefono': o.telefono,
            'messaggio': (f"🛒 ORDINE #{o.id} DAL NEGOZIO ONLINE\n"
                          f"Prodotto: {o.prodotto.nome} x{o.quantita}\n"
                          f"Totale: {o.totale_eur} EUR ({o.metodo_pagamento})\n"
                          f"Spedizione: {o.indirizzo}, {o.cap} {o.citta} ({o.provincia})"),
            'fonte': 'Negozio Online - mauriziogustinicchiconsulting.it',
            'data': datetime.now().isoformat(),
        }
        headers = {'Content-Type': 'application/json'}
        if CRM_API_KEY:
            headers['X-API-Key'] = CRM_API_KEY
        try:
            r = requests.post(CRM_WEBHOOK_URL, json=payload, headers=headers, timeout=10)
            o.sincronizzato_crm = r.status_code in (200, 201)
            db.session.commit()
        except Exception as e:
            print(f'CRM ordine {ordine_id}: {e}')


@app.route('/negozio')
def negozio():
    prodotti = Prodotto.query.filter_by(attivo=True).order_by(Prodotto.tipo, Prodotto.nome).all()
    return render_template('negozio.html', prodotti=prodotti)


@app.route('/acquista/<slug>', methods=['GET', 'POST'])
def acquista(slug):
    p = Prodotto.query.filter_by(slug=slug, attivo=True).first_or_404()

    if request.method == 'POST':
        try:
            qty = max(1, min(20, int(request.form.get('quantita', 1))))
        except ValueError:
            qty = 1
        totale = p.prezzo_cent * qty + p.spedizione_cent

        ordine = Ordine(
            prodotto_id=p.id, quantita=qty, totale_cent=totale,
            nome=request.form.get('nome', '').strip(),
            email=request.form.get('email', '').strip(),
            telefono=request.form.get('telefono', '').strip(),
            indirizzo=request.form.get('indirizzo', '').strip(),
            cap=request.form.get('cap', '').strip(),
            citta=request.form.get('citta', '').strip(),
            provincia=request.form.get('provincia', '').strip().upper()[:2],
            note=request.form.get('note', '').strip(),
        )
        if not ordine.nome or not ordine.email or not ordine.indirizzo or not ordine.citta:
            flash('Compila tutti i campi obbligatori (nome, email, indirizzo, città).', 'error')
            return redirect(url_for('acquista', slug=slug))

        if STRIPE_SECRET_KEY:
            # --- Pagamento con carta via Stripe Checkout ---
            ordine.metodo_pagamento = 'stripe'
            ordine.stato = 'in_attesa_pagamento'
            db.session.add(ordine)
            db.session.commit()
            import stripe
            sess = stripe.checkout.Session.create(
                mode='payment',
                line_items=[
                    {'price_data': {'currency': 'eur',
                                    'product_data': {'name': p.nome},
                                    'unit_amount': p.prezzo_cent},
                     'quantity': qty},
                    {'price_data': {'currency': 'eur',
                                    'product_data': {'name': 'Spedizione'},
                                    'unit_amount': p.spedizione_cent},
                     'quantity': 1},
                ],
                customer_email=ordine.email,
                metadata={'ordine_id': ordine.id},
                success_url=f'{SITE_URL}/ordine/{ordine.id}/successo',
                cancel_url=f'{SITE_URL}/ordine/{ordine.id}/annullato',
            )
            ordine.stripe_session_id = sess.id
            db.session.commit()
            return redirect(sess.url, code=303)
        else:
            # --- Modalità bonifico: raccolgo l'ordine, pagamento offline ---
            ordine.metodo_pagamento = 'bonifico'
            ordine.stato = 'da_confermare'
            db.session.add(ordine)
            db.session.commit()
            threading.Thread(target=invia_ordine_al_crm, args=(ordine.id,), daemon=True).start()
            return redirect(url_for('ordine_esito', ordine_id=ordine.id, esito='bonifico'))

    return render_template('checkout.html', p=p)


@app.route('/ordine/<int:ordine_id>/<esito>')
def ordine_esito(ordine_id, esito):
    o = Ordine.query.get_or_404(ordine_id)
    if esito not in ('successo', 'annullato', 'bonifico'):
        abort(404)
    return render_template('ordine_esito.html', o=o, esito=esito,
                           iban=IBAN_BONIFICO, intestatario=INTESTATARIO_BONIFICO)


@app.route('/webhook/stripe', methods=['POST'])
def webhook_stripe():
    """Stripe chiama questo endpoint quando il pagamento va a buon fine."""
    if not STRIPE_SECRET_KEY:
        abort(404)
    import stripe
    payload = request.get_data()
    sig = request.headers.get('Stripe-Signature', '')
    try:
        if STRIPE_WEBHOOK_SECRET:
            event = stripe.Webhook.construct_event(payload, sig, STRIPE_WEBHOOK_SECRET)
        else:
            event = json.loads(payload)
    except Exception as e:
        return Response(f'Webhook non valido: {e}', status=400)

    if event.get('type') == 'checkout.session.completed':
        sess = event['data']['object']
        ordine_id = (sess.get('metadata') or {}).get('ordine_id')
        o = Ordine.query.get(int(ordine_id)) if ordine_id else None
        if o and o.stato == 'in_attesa_pagamento':
            o.stato = 'pagato'
            db.session.commit()
            threading.Thread(target=invia_ordine_al_crm, args=(o.id,), daemon=True).start()
    return Response('ok', status=200)


# --- Admin negozio ---
@app.route('/admin/prodotti', methods=['GET', 'POST'])
@login_required
def admin_prodotti():
    if request.method == 'POST':
        pid = request.form.get('id')
        p = Prodotto.query.get(int(pid)) if pid else Prodotto()
        if not pid:
            db.session.add(p)
        p.slug = request.form.get('slug', '').strip()
        p.nome = request.form.get('nome', '').strip()
        p.descrizione = request.form.get('descrizione', '').strip()
        p.tipo = request.form.get('tipo', 'libro')
        p.immagine = request.form.get('immagine', '').strip()
        p.attivo = request.form.get('attivo') == 'on'
        try:
            p.prezzo_cent = int(round(float(request.form.get('prezzo', '0').replace(',', '.')) * 100))
            p.spedizione_cent = int(round(float(request.form.get('spedizione', '0').replace(',', '.')) * 100))
        except ValueError:
            flash('Prezzo non valido.', 'error')
            return redirect(url_for('admin_prodotti'))
        db.session.commit()
        flash('Prodotto salvato.', 'success')
        return redirect(url_for('admin_prodotti'))
    prodotti = Prodotto.query.order_by(Prodotto.tipo, Prodotto.nome).all()
    return render_template('admin/prodotti.html', prodotti=prodotti)


@app.route('/admin/ordini')
@login_required
def admin_ordini():
    ordini = Ordine.query.order_by(Ordine.creato_il.desc()).limit(200).all()
    return render_template('admin/ordini.html', ordini=ordini)


@app.route('/admin/ordine/<int:ordine_id>/stato', methods=['POST'])
@login_required
def admin_ordine_stato(ordine_id):
    o = Ordine.query.get_or_404(ordine_id)
    nuovo = request.form.get('stato', '')
    if nuovo in ('da_confermare', 'in_attesa_pagamento', 'pagato', 'spedito', 'annullato'):
        o.stato = nuovo
        db.session.commit()
        flash(f'Ordine #{o.id} → {nuovo}.', 'success')
    return redirect(url_for('admin_ordini'))


def seed_prodotti():
    if Prodotto.query.count() > 0:
        return
    libri = [
        dict(slug='marketing-di-successo', tipo='libro',
             nome='MARKETING DI SUCCESSO: Costi e Controllo nella Tua Strategia',
             descrizione='Manuale operativo per Imprenditori e Controller: misura le campagne marketing e trasforma la spesa in investimento strategico. Copia cartacea autografata.',
             prezzo_cent=2490, spedizione_cent=500,
             immagine='/static/img/libro-marketing-successo.jpg'),
        dict(slug='professionista-segreteria-ceo', tipo='libro',
             nome="IL PROFESSIONISTA QUALIFICATO DI SEGRETERIA E L'ASSISTENTE DEL CEO",
             descrizione='Competenze, strategie e successo per la figura chiave accanto alla direzione. Copia cartacea autografata.',
             prezzo_cent=2490, spedizione_cent=500,
             immagine='/static/img/libro-executive-assistant.jpg'),
        dict(slug='distruzione-creatrice-4-0', tipo='libro',
             nome="LA DISTRUZIONE CREATRICE 4.0: COMANDARE L'AI PER MARGINALIZZARE",
             descrizione="Come guidare l'Intelligenza Artificiale per creare margine e vantaggio competitivo. Copia cartacea autografata.",
             prezzo_cent=2490, spedizione_cent=500,
             immagine='/static/img/libro-la-distruzione-creatrice.jpg'),
    ]
    for l in libri:
        db.session.add(Prodotto(**l))
    db.session.commit()
    print(f'>>> Seed prodotti: {len(libri)} libri.')



# =====================================================================
# INIT DB + SEED AUTOMATICO AL PRIMO AVVIO
# =====================================================================
def ensure_editorial_article_columns():
    """Add integration columns to a legacy ``articoli`` table without data loss.

    ``create_all`` only creates missing tables; it never alters a production table.
    This deliberately small, additive migration works on SQLite and PostgreSQL and
    is safe to run on every process startup.
    """
    inspector = inspect(db.engine)
    if 'articoli' not in inspector.get_table_names():
        return
    existing = {column['name'] for column in inspector.get_columns('articoli')}
    binary_type = 'BYTEA' if db.engine.dialect.name == 'postgresql' else 'BLOB'
    additions = {
        'external_id': 'VARCHAR(36)',
        'version': 'INTEGER DEFAULT 1',
        'payload_hash': 'VARCHAR(64)',
        'updated_at': 'TIMESTAMP',
        'traccia_input': "TEXT DEFAULT ''",
        'pubblico_target': "VARCHAR(200) DEFAULT ''",
        'tono_voce': "VARCHAR(100) DEFAULT 'Professionale e concreto'",
        'autore': "VARCHAR(160) DEFAULT 'Maurizio Gustinicchi'",
        'stato': 'VARCHAR(20)',
        'published_at': 'TIMESTAMP',
        'image_prompt': "TEXT DEFAULT ''",
        'cover_filename': "VARCHAR(240) DEFAULT ''",
        'cover_mimetype': "VARCHAR(80) DEFAULT ''",
        'cover_data': binary_type,
    }
    with db.engine.begin() as connection:
        for column, definition in additions.items():
            if column not in existing:
                connection.execute(text(f'ALTER TABLE articoli ADD COLUMN {column} {definition}'))
        # Allinea lo stato esplicito agli articoli storici senza cambiare la
        # loro visibilità e conserva una data attendibile per quelli pubblicati.
        connection.execute(text(
            "UPDATE articoli SET stato = CASE WHEN pubblicato THEN 'pubblicato' ELSE 'bozza' END "
            "WHERE stato IS NULL OR stato = ''"
        ))
        connection.execute(text(
            "UPDATE articoli SET published_at = COALESCE(updated_at, creato_il) "
            "WHERE pubblicato = TRUE AND published_at IS NULL"
        ))
        # Multiple NULL external_id values are valid for pre-existing articles.
        connection.execute(text(
            'CREATE UNIQUE INDEX IF NOT EXISTS ix_articoli_external_id '
            'ON articoli (external_id)'
        ))


def seed_articoli():
    """Importa soltanto gli articoli del seed che non sono già presenti."""
    seed_file = os.path.join(os.path.dirname(__file__), 'seed_articoli.json')
    if not os.path.exists(seed_file):
        return
    with open(seed_file, encoding='utf-8') as f:
        articoli = json.load(f)
    inseriti = 0
    for a in articoli:
        if Articolo.query.filter_by(slug=a['slug']).first():
            continue
        db.session.add(Articolo(
            slug=a['slug'], titolo=a['titolo'],
            meta_description=a.get('meta_description', ''),
            excerpt=a.get('excerpt', ''),
            cover=a.get('cover', ''),
            body=a['body'], styles=a.get('styles', ''),
            data_pubblicazione=date.fromisoformat(a['data_pubblicazione']),
            pubblicato=True))
        inseriti += 1
    if inseriti:
        db.session.commit()
        print(f'>>> Seed completato: {inseriti} nuovi articoli importati.')


def initialize_database_safely():
    """Serializza schema e seed quando Gunicorn avvia più worker insieme."""
    if db.engine.dialect.name == 'postgresql':
        # Lock di sessione: resta attivo anche se create_all/ALTER usano altre
        # transazioni e viene rilasciato esplicitamente alla fine del seed.
        lock_id = 684731902
        db.session.execute(text('SELECT pg_advisory_lock(:lock_id)'), {'lock_id': lock_id})
        try:
            db.create_all()
            ensure_editorial_article_columns()
            seed_articoli()
            seed_prodotti()
        finally:
            db.session.execute(text('SELECT pg_advisory_unlock(:lock_id)'), {'lock_id': lock_id})
            db.session.commit()
    else:
        # Railway usa PostgreSQL; questo lock rende sicuri anche test e avvii
        # locali SQLite con più processi contemporanei.
        import fcntl
        lock_path = os.path.join('/tmp', 'mgc-website-schema.lock')
        with open(lock_path, 'w') as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                db.create_all()
                ensure_editorial_article_columns()
                seed_articoli()
                seed_prodotti()
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


with app.app_context():
    initialize_database_safely()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
