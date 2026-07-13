# -*- coding: utf-8 -*-
"""
MAURIZIO GUSTINICCHI CONSULTING - Sito dinamico
Flask + PostgreSQL (Railway) | Blog gestito da DB | Form contatti -> CRM
"""
import os
import re
import json
import threading
from datetime import datetime, date
from functools import wraps

import requests
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, abort, Response)
from models import db, Articolo, Lead, Prodotto, Ordine

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'mgc-dev-key-cambiami')

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

SITE_URL = os.environ.get('SITE_URL', 'https://www.mauriziogustinicchiconsulting.it')


@app.context_processor
def inject_globals():
    return {'current_year': datetime.now().year}


@app.after_request
def converti_grassetto_markdown(response):
    """Il sito contiene testi scritti in stile Markdown (**parola**) che però
    non vengono interpretati da Jinja, quindi comparivano gli asterischi
    letterali. Qui li convertiamo in <strong> su tutto l'HTML in uscita,
    così non serve correggere ogni singolo template a mano (né i futuri
    articoli di blog/prodotti scritti allo stesso modo)."""
    if response.content_type and 'text/html' in response.content_type:
        html = response.get_data(as_text=True)
        html = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', html, flags=re.S)
        response.set_data(html)
    return response


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
                .order_by(Articolo.data_pubblicazione.desc())
                .all())
    return render_template('blog_lista.html', articoli=articoli)


@app.route('/blog/<slug>')
def blog_articolo(slug):
    articolo = Articolo.query.filter_by(slug=slug, pubblicato=True).first_or_404()
    return render_template('blog_articolo.html', a=articolo)


# =====================================================================
# CONTATTI: salva lead su DB + invio al CRM via webhook
# =====================================================================
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

        flash('Messaggio inviato con successo! Ti risponderò al più presto.', 'success')
        return redirect(url_for('contatti'))

    return render_template('contatti.html')




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
    for a in Articolo.query.filter_by(pubblicato=True).all():
        urls.append(f'{SITE_URL}/blog/{a.slug}')
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
# PANNELLO ADMIN (blog + lead)
# =====================================================================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('admin_login'))
        return f(*args, **kwargs)
    return wrapper


@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
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
        if not articolo:
            articolo = Articolo()
            db.session.add(articolo)
        articolo.slug = request.form.get('slug', '').strip()
        articolo.titolo = request.form.get('titolo', '').strip()
        articolo.meta_description = request.form.get('meta_description', '').strip()
        articolo.excerpt = request.form.get('excerpt', '').strip()
        articolo.cover = request.form.get('cover', '').strip()
        articolo.body = request.form.get('body', '')
        articolo.styles = request.form.get('styles', '')
        articolo.pubblicato = request.form.get('pubblicato') == 'on'
        data_str = request.form.get('data_pubblicazione', '')
        if data_str:
            articolo.data_pubblicazione = date.fromisoformat(data_str)
        db.session.commit()
        flash('Articolo salvato.', 'success')
        return redirect(url_for('admin_dashboard'))
    return render_template('admin/articolo_form.html', a=articolo)


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

        # --- SOFTWARE: prenotazione/richiesta demo, niente spedizione né pagamento online ---
        if p.tipo == 'software':
            ordine = Ordine(
                prodotto_id=p.id, quantita=1, totale_cent=0,
                nome=request.form.get('nome', '').strip(),
                email=request.form.get('email', '').strip(),
                telefono=request.form.get('telefono', '').strip(),
                citta=request.form.get('azienda', '').strip(),  # riuso il campo 'citta' per l'azienda del richiedente
                note=request.form.get('note', '').strip(),
                metodo_pagamento='prenotazione',
                stato='da_confermare',
            )
            if not ordine.nome or not ordine.email:
                flash('Compila almeno nome ed email per la prenotazione.', 'error')
                return redirect(url_for('acquista', slug=slug))
            db.session.add(ordine)
            db.session.commit()
            threading.Thread(target=invia_ordine_al_crm, args=(ordine.id,), daemon=True).start()
            return redirect(url_for('ordine_esito', ordine_id=ordine.id, esito='prenotazione'))

        # --- LIBRO: acquisto vero con spedizione e pagamento ---
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
    if esito not in ('successo', 'annullato', 'bonifico', 'prenotazione'):
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
             nome='LA RAGIONERIA DEL MARGINE PER ADDETTI AL MARKETING (Nuova Edizione)',
             descrizione="Il nuovo Marketer-Controller AI-Driven: Modello AI-Driven per la costificazione, Ragioneria Strategica e Analisi Predittiva del budget marketing. Copia cartacea autografata.",
             prezzo_cent=2490, spedizione_cent=500,
             immagine='/static/img/libro-ragioneria-margine-marketing.jpg'),
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

    software = [
        dict(slug='mastercash', tipo='software', nome='MasterCash',
             descrizione='Tesoreria & Cash Flow: pianificazione finanziaria a livello CFO, scadenzario attivo/passivo, previsione di cassa a 12 mesi.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/mastercash.jpg'),
        dict(slug='mastercpm', tipo='software', nome='MasterCPM',
             descrizione='Corporate Performance Management: bilancio previsionale, conto economico riclassificato, cash flow indiretto.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/mastercpm.jpg'),
        dict(slug='masterdebt', tipo='software', nome='MasterDebt',
             descrizione='Rateizzazioni & Debito Fiscale: cartelle esattoriali e piani di rateizzazione AdER/INPS in un\'unica dashboard.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/masterdebt.jpg'),
        dict(slug='masterledger', tipo='software', nome='MasterLedger',
             descrizione='Contabilità & Fatturazione Elettronica: ciclo attivo e passivo, fatture multi-riga, import XML/p7m dallo SdI.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/masterledger.jpg'),
        dict(slug='masterwork', tipo='software', nome='MasterWork',
             descrizione='Produzione & Fabbrica: tracciatura avanzamenti e anomalie di reparto, gestione operatori e turni.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/masterwork.jpg'),
        dict(slug='masterlogistic-wms', tipo='software', nome='MasterLogistic / MasterWMS',
             descrizione='Magazzino & Logistica: ordini fornitori/clienti, DDT, giacenze, flussi corrieri e KPI logistici in tempo reale.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/masterlogistic-wms.jpg'),
        dict(slug='masteranalytics', tipo='software', nome='MasterAnalytics',
             descrizione='Analisi & Marginalità: analytics di produzione integrata via API, costi, ricavi, marginalità per articolo.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/masteranalytics.jpg'),
        dict(slug='masterquality', tipo='software', nome='MasterQuality',
             descrizione='Qualità ISO 9001 / IATF: non conformità, audit, APQP/PPAP e documentazione di sistema.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/masterquality.jpg'),
        dict(slug='masterprocurement', tipo='software', nome='MasterProcurement',
             descrizione='Acquisti: richieste d\'acquisto, ordini e vendor rating con flussi approvativi digitali.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/masterprocurement.jpg'),
        dict(slug='masterproduction', tipo='software', nome='MasterProduction',
             descrizione='Pianificazione: programmazione della produzione con visibilità su capacità, priorità e colli di bottiglia.',
             prezzo_cent=0, spedizione_cent=0, immagine='/static/img/master-suite/masterproduction.jpg'),
    ]
    for s in software:
        db.session.add(Prodotto(**s))

    db.session.commit()
    print(f'>>> Seed prodotti: {len(libri)} libri + {len(software)} software.')



# =====================================================================
# INIT DB + SEED AUTOMATICO AL PRIMO AVVIO
# =====================================================================
def seed_articoli():
    if Articolo.query.count() > 0:
        return
    seed_file = os.path.join(os.path.dirname(__file__), 'seed_articoli.json')
    if not os.path.exists(seed_file):
        return
    with open(seed_file, encoding='utf-8') as f:
        articoli = json.load(f)
    for a in articoli:
        db.session.add(Articolo(
            slug=a['slug'], titolo=a['titolo'],
            meta_description=a.get('meta_description', ''),
            excerpt=a.get('excerpt', ''),
            cover=a.get('cover', ''),
            body=a['body'], styles=a.get('styles', ''),
            data_pubblicazione=date.fromisoformat(a['data_pubblicazione']),
            pubblicato=True))
    db.session.commit()
    print(f'>>> Seed completato: {len(articoli)} articoli importati.')


with app.app_context():
    db.create_all()
    seed_articoli()
    seed_prodotti()


if __name__ == '__main__':
    app.run(debug=True, port=5000)
