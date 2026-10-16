# -*- coding: utf-8 -*-
"""
AGENTE AI del sito — sostituisce l'app Streamlit esterna.
La base di conoscenza viene costruita direttamente dai contenuti del sito:
- template delle pagine (chi-siamo, servizi, formazione, certificati)
- articoli del blog letti LIVE dal database (sempre aggiornati)
- prodotti del negozio letti dal database
Chiamata a Gemini via REST (nessun SDK necessario).
"""
import os
import re
import requests

GEMINI_API_KEY = os.environ.get('GEMINI_API_KEY', '')
GEMINI_MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.0-flash')
GEMINI_URL = (f'https://generativelanguage.googleapis.com/v1beta/models/'
              f'{GEMINI_MODEL}:generateContent')

_TEMPLATE_SORGENTI = [
    'templates/chi-siamo.html',
    'templates/certificati.html',
    'templates/servizi.html',
    'templates/formazione.html',
    'templates/servizi/controllo.html',
    'templates/servizi/digitalizzazione.html',
    'templates/servizi/innovation-manager.html',
    'templates/servizi/business-reporting.html',
    'templates/servizi/organizzazione.html',
    'templates/servizi/dashboard-bi.html',
    'templates/servizi/manutenzione.html',
    'templates/servizi/content-factory.html',
    'templates/shop.html',  # Master Suite: i programmi che Maurizio progetta e installa
]


def _html_a_testo(html):
    """Estrae il testo leggibile da un template, buttando via tag, style e jinja."""
    html = re.sub(r'<style[^>]*>.*?</style>', ' ', html, flags=re.S)
    html = re.sub(r'<script[^>]*>.*?</script>', ' ', html, flags=re.S)
    html = re.sub(r'\{%.*?%\}', ' ', html, flags=re.S)
    html = re.sub(r'\{\{.*?\}\}', ' ', html, flags=re.S)
    html = re.sub(r'<[^>]+>', ' ', html)
    html = re.sub(r'\s+', ' ', html)
    return html.strip()


_cache_pagine = None


def _conoscenza_pagine():
    """Testo delle pagine statiche (cache: cambia solo con un nuovo deploy)."""
    global _cache_pagine
    if _cache_pagine is not None:
        return _cache_pagine
    base = os.path.dirname(os.path.abspath(__file__))
    blocchi = []
    for rel in _TEMPLATE_SORGENTI:
        p = os.path.join(base, rel)
        if os.path.exists(p):
            with open(p, encoding='utf-8') as f:
                testo = _html_a_testo(f.read())
            nome = rel.replace('templates/', '').replace('.html', '')
            limite = 9000 if nome == 'shop' else 4000  # la Master Suite non va tagliata
            blocchi.append(f'--- PAGINA: {nome} ---\n{testo[:limite]}')
    _cache_pagine = '\n\n'.join(blocchi)
    return _cache_pagine


def costruisci_conoscenza():
    """Base di conoscenza completa: pagine + blog e prodotti letti dal DB ora."""
    from models import Articolo, Prodotto
    parti = [_conoscenza_pagine()]

    articoli = (Articolo.query.filter_by(pubblicato=True)
                .order_by(Articolo.data_pubblicazione.desc()).limit(10).all())
    for a in articoli:
        corpo = _html_a_testo(a.body)[:2500]
        parti.append(f'--- ARTICOLO BLOG ({a.data_it}): {a.titolo} ---\n{corpo}')

    prodotti = Prodotto.query.filter_by(attivo=True).all()
    if prodotti:
        righe = [f'- {p.nome} | {p.tipo} | € {p.prezzo_eur} + € {p.spedizione_eur} '
                 f'spedizione | acquistabile su /acquista/{p.slug}'
                 for p in prodotti]
        parti.append('--- PRODOTTI IN VENDITA DIRETTA SUL SITO ---\n' + '\n'.join(righe))

    return '\n\n'.join(parti)


ISTRUZIONI = """Sei l'Agente AI Strategico di Maurizio Gustinicchi Consulting \
(www.mauriziogustinicchiconsulting.it). Maurizio è un ingegnere AI e Industrial \
Controller/CFO con 30 anni di esperienza: crea algoritmi di intelligenza artificiale \
su misura per Controllo di Gestione, forecast, anomaly detection, manutenzione \
predittiva e marketing per PMI italiane. È Innovation Manager certificato DNV \
(UNI 11814 / ISO 56002).

Maurizio PROGETTA, SVILUPPA E INSTALLA PROGRAMMI INFORMATICI PER LE AZIENDE: gestionali \
ed ERP su misura e i programmi della Master Suite (pagina /shop: MasterCRM, MasterPricing, \
MasterLedger, MasterWork, MasterLogistic, MasterProduction, MasterQuality, MasterCash e \
gli altri). Il suo metodo è la CO-PROGETTAZIONE con il cliente: non si parte dal software \
ma dal problema; insieme si analizza come lavora davvero l'azienda (reparti, passaggi, \
dati ricopiati), poi si decide cosa integrare, personalizzare o sviluppare da zero, e il \
programma viene installato e messo in uso con le persone che lo useranno.

Regole:
- Rispondi in italiano, tono professionale ma diretto, risposte concise (max 150 parole).
- Basa le risposte SOLO sulla base di conoscenza fornita. Se non sai, dillo e \
suggerisci di scrivere dalla pagina /contatti.
- Se l'utente descrive un problema operativo (dati ricopiati, magazzino che non torna, \
preventivi non seguiti, prezzi o margini poco chiari, commesse di cui non si sa lo \
stato...), spiega che Maurizio lo affronta con la co-progettazione e, se c'è, cita il \
programma della Master Suite più vicino al problema, senza promettere risultati.
- Quando pertinente, invita a raccontare il problema dalla pagina /contatti, a \
richiedere una demo dei programmi (/shop) o a fissare la Consulenza Strategica gratuita; \
segnala i libri acquistabili sul sito (/negozio) solo se l'argomento è quello.
- Non inventare prezzi, ROI o dati non presenti nella conoscenza.
"""


def chiedi_agente(messaggio, storia=None):
    """storia: lista [{'ruolo': 'utente'|'agente', 'testo': ...}]"""
    if not GEMINI_API_KEY:
        return ("L'agente AI non è al momento configurato. "
                "Scrivimi dalla pagina Contatti e ti rispondo personalmente!")

    conoscenza = costruisci_conoscenza()
    contents = []
    for turno in (storia or [])[-8:]:
        ruolo = 'user' if turno.get('ruolo') == 'utente' else 'model'
        contents.append({'role': ruolo, 'parts': [{'text': str(turno.get('testo', ''))[:1500]}]})
    contents.append({'role': 'user', 'parts': [{'text': str(messaggio)[:2000]}]})

    payload = {
        'system_instruction': {'parts': [{'text': ISTRUZIONI +
                                          '\n\n=== BASE DI CONOSCENZA ===\n' + conoscenza}]},
        'contents': contents,
        'generationConfig': {'temperature': 0.4, 'maxOutputTokens': 500},
    }
    try:
        r = requests.post(GEMINI_URL, params={'key': GEMINI_API_KEY},
                          json=payload, timeout=25)
        r.raise_for_status()
        data = r.json()
        return data['candidates'][0]['content']['parts'][0]['text'].strip()
    except Exception as e:
        print(f'❌ Agente AI: {e}')
        return ("In questo momento non riesco a rispondere. "
                "Riprova tra poco oppure scrivici dalla pagina /contatti.")
