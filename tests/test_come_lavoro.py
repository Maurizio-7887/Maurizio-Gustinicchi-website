"""Test isolati: nessun avvio dell'applicazione reale o accesso a DB/CRM."""
import ast
from datetime import date
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from flask import Flask, abort, redirect, render_template, Response, url_for

ROOT = Path(__file__).resolve().parents[1]

def isolated_app():
    app = Flask(__name__, template_folder=str(ROOT/'templates'), static_folder=str(ROOT/'static'))
    app.secret_key = 'isolated-render-only'
    app.context_processor(lambda: dict(current_year=2026))
    source = ast.parse((ROOT/'app.py').read_text())
    names = {'pagina_statica', 'sitemap', 'redirect_pagina_html'}
    # Only the actual static handler, page lists and sitemap; no startup code.
    nodes = [n for n in source.body if
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id in {'PAGINE','SERVIZI_DETTAGLIO'} for t in n.targets)) or
             (isinstance(n, ast.FunctionDef) and n.name in names)]
    class EmptyQuery:
        def filter_by(self, **kwargs): return self
        def filter(self, *args): return self
        def all(self): return []
    class FakeDateColumn:
        def __le__(self, other): return True
    scope = dict(app=app, abort=abort, redirect=redirect, render_template=render_template,
                 Response=Response, url_for=url_for, SITE_URL='https://www.mauriziogustinicchiconsulting.it',
                 Articolo=SimpleNamespace(query=EmptyQuery(), data_pubblicazione=FakeDateColumn()),
                 LandingPage=SimpleNamespace(query=EmptyQuery()), date=date)
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'isolated-static-pages', 'exec'), scope)
    return app

class ComeLavoroTest(unittest.TestCase):
    def setUp(self): self.app = isolated_app(); self.client = self.app.test_client()
    def html(self): return self.client.get('/come-lavoro').get_data(as_text=True)
    def test_actual_static_handler_serves_page(self):
        self.assertEqual(self.client.get('/come-lavoro').status_code, 200)
    def test_one_h1_and_unique_message(self):
        h = self.html()
        self.assertEqual(len(re.findall(r'<h1[ >]', h)), 1)
        for text in ['Prima entro nella tua azienda.', 'responsabili e agli operatori', 'User friendly', 'WhatsApp']:
            self.assertIn(text, h)
    def test_main_navigation_opens_dedicated_page(self):
        h = self.html()
        self.assertIn('href="/come-lavoro">Come lavoro</a>', h)
        self.assertNotIn('href="/#come-lavoro"', h)
    def test_canonical_and_metadata(self):
        h = self.html()
        self.assertIn('href="https://www.mauriziogustinicchiconsulting.it/come-lavoro"', h)
        self.assertIn('Come lavoro: in azienda, al tuo fianco', h)
        self.assertIn('name="description"', h)
    def test_contact_destination_preserved(self):
        h = self.html()
        self.assertEqual(h.count('href="/contatti#richiesta"'), 2)
        self.assertIn('href="/servizi"', h)
    def test_placeholder_no_client_chat_or_response_guarantee(self):
        h = self.html()
        self.assertIn('segnaposto temporaneo', h)
        self.assertIn('tempi di risposta si concordano', h)
        self.assertNotIn('7 minuti', h)
        self.assertNotIn('image.png', h)
        self.assertNotIn('<img', h)
    def test_no_extra_tracking_or_forms(self):
        h = self.html()
        self.assertNotIn('<form', h)
        self.assertNotIn('fbq(', h)
        self.assertNotIn('gtag(', h)
    def test_page_in_actual_sitemap(self):
        xml = self.client.get('/sitemap.xml').get_data(as_text=True)
        self.assertIn('<loc>https://www.mauriziogustinicchiconsulting.it/come-lavoro</loc>', xml)
    def test_unknown_page_still_404(self):
        self.assertEqual(self.client.get('/not-a-page').status_code, 404)

if __name__ == '__main__': unittest.main()
