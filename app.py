# -*- coding: utf-8 -*-
"""
MAURIZIO GUSTINICCHI CONSULTING - Sito dinamico
Flask + PostgreSQL (Railway) | Blog gestito da DB | Form contatti -> CRM
"""
import os
import json
import threading
from datetime import datetime, date
from functools import wraps

import requests
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, abort, Response)
from models import db, Articolo, Lead

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

# --- Admin ---
ADMIN_USER = os.environ.get('ADMIN_USER', 'maurizio')
ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD', 'Mgc@Admin2026!')

SITE_URL = os.environ.get('SITE_URL', 'https://www.mauriziogustinicchiconsulting.it')


@app.context_processor
def inject_globals():
    return {'current_year': datetime.now().year}


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
    urls += [f'{SITE_URL}/blog', f'{SITE_URL}/contatti']
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


if __name__ == '__main__':
    app.run(debug=True, port=5000)
