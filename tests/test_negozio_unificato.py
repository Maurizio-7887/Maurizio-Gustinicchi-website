"""Test isolati: solo SQLite in memoria, niente app completa, rete o pagamenti."""
import ast
import unittest
from datetime import date
from pathlib import Path
from types import SimpleNamespace

from flask import Flask, abort, redirect, render_template, url_for, request, flash
from flask_sqlalchemy import SQLAlchemy
from catalogo_libri import CATALOGO_LIBRI, aggiorna_libri

ROOT = Path(__file__).resolve().parents[1]


def isolated_app():
    app = Flask(__name__, template_folder=str(ROOT / 'templates'))
    app.config.update(TESTING=True, SECRET_KEY='isolated-test', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    db = SQLAlchemy(app)
    class Prodotto(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        slug = db.Column(db.String, unique=True)
        tipo = db.Column(db.String)
        nome = db.Column(db.String)
        descrizione = db.Column(db.String)
        immagine = db.Column(db.String)
        attivo = db.Column(db.Boolean, default=True)
        prezzo_cent = db.Column(db.Integer)
        spedizione_cent = db.Column(db.Integer)
        @property
        def prezzo_eur(self):
            return f'{self.prezzo_cent / 100:.2f}'.replace('.', ',')
        @property
        def spedizione_eur(self):
            return f'{self.spedizione_cent / 100:.2f}'.replace('.', ',')
    class Ordine(db.Model):
        id = db.Column(db.Integer, primary_key=True)
        prodotto_id = db.Column(db.Integer)
        quantita = db.Column(db.Integer)
        totale_cent = db.Column(db.Integer)
        metodo_pagamento = db.Column(db.String)
        stato = db.Column(db.String)
        nome = db.Column(db.String)
        email = db.Column(db.String)
        telefono = db.Column(db.String)
        indirizzo = db.Column(db.String)
        cap = db.Column(db.String)
        citta = db.Column(db.String)
        provincia = db.Column(db.String)
        note = db.Column(db.String)
    scope = dict(app=app, redirect=redirect, url_for=url_for, abort=abort, render_template=render_template,
                 Prodotto=Prodotto, Ordine=Ordine, db=db, request=request, flash=flash, STRIPE_SECRET_KEY='',
                 threading=SimpleNamespace(Thread=lambda **kw: SimpleNamespace(start=lambda: None)),
                 invia_ordine_al_crm=lambda *a: None)
    tree = ast.parse((ROOT / 'app.py').read_text())
    nodes = [n for n in tree.body if
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'PAGINE' for t in n.targets)) or
             (isinstance(n, ast.FunctionDef) and n.name in {'pagina_statica', 'negozio', 'acquista'})]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'isolated-routes', 'exec'), scope)
    app.add_url_rule('/ordine/<int:ordine_id>/<esito>', 'ordine_esito', lambda **kw: 'OK')
    app.jinja_env.globals.update(current_year=date.today().year)
    return app, db, Prodotto, Ordine


class NegozioTests(unittest.TestCase):
    def setUp(self):
        self.app, self.db, self.Product, self.Order = isolated_app()
        self.ctx = self.app.app_context(); self.ctx.push()
        self.db.create_all()
        for slug in CATALOGO_LIBRI:
            self.db.session.add(self.Product(slug=slug, tipo='libro', nome='Titolo precedente', descrizione='Precedente',
                                            immagine='/old.jpg', prezzo_cent=2490, spedizione_cent=500))
        self.db.session.add(self.Product(slug='software-test', tipo='software', nome='Software sintetico',
                                        descrizione='Test', prezzo_cent=12000, spedizione_cent=0))
        self.db.session.add(self.Order(prodotto_id=1, totale_cent=2990, quantita=1, stato='pagato'))
        self.db.session.commit()
        self.client = self.app.test_client()

    def tearDown(self):
        self.db.session.remove(); self.db.drop_all(); self.ctx.pop()

    def apply(self):
        return aggiorna_libri(self.db.session, self.Product, applica=True)

    def test_dry_run_does_not_modify(self):
        report = aggiorna_libri(self.db.session, self.Product)
        self.assertEqual(len(report), 3)
        self.assertEqual(self.Product.query.filter_by(tipo='libro').first().prezzo_cent, 2490)
        self.assertFalse(self.db.session.dirty)

    def test_apply_titles_images_and_prices(self):
        self.apply()
        for slug, expected in CATALOGO_LIBRI.items():
            p = self.Product.query.filter_by(slug=slug).one()
            for k, v in expected.items(): self.assertEqual(getattr(p, k), v)
            self.assertEqual(p.spedizione_cent, 500)

    def test_idempotent(self):
        self.apply(); report = self.apply()
        self.assertTrue(all(not r['campi'] for r in report))

    def test_no_software_or_order_changes(self):
        self.apply()
        self.assertEqual(self.Product.query.filter_by(slug='software-test').one().prezzo_cent, 12000)
        self.assertEqual(self.Order.query.one().totale_cent, 2990)
        self.assertEqual(self.Order.query.one().stato, 'pagato')

    def test_missing_and_inactive_books(self):
        p = self.Product.query.filter_by(slug='marketing-di-successo').one()
        p.attivo = False
        self.db.session.delete(self.Product.query.filter_by(slug='distruzione-creatrice-4-0').one())
        self.db.session.commit()
        report = self.apply()
        self.assertEqual(sum(r['mancante'] for r in report), 1)
        self.assertFalse(p.attivo)
        self.assertEqual(self.Product.query.count(), 3)

    def test_unified_catalog_and_navigation(self):
        self.apply(); html = self.client.get('/negozio').get_data(as_text=True)
        self.assertIn('LA RAGIONERIA DEL MARGINE', html)
        self.assertIn('libro-ragioneria-margine-marketing.jpg', html)
        self.assertIn('59,00', html); self.assertIn('49,00', html); self.assertIn('79,00', html)
        self.assertNotIn('24,90', html)
        for name in ('MasterCash', 'MasterCRM', 'MasterProduction', 'Software sintetico'):
            self.assertIn(name, html)
        self.assertEqual(html.count('>NEGOZIO</a>'), 1)
        self.assertNotIn('>ACQUISTA</a>', html)
        self.assertIn('>LIBRI</a>', html)
        self.assertEqual(html.count('<h1>'), 1)
        self.assertIn('google-site-verification', html)

    def test_legacy_shop_redirect(self):
        response = self.client.get('/shop')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers['Location'], '/negozio#software')

    def test_software_prices_are_on_request(self):
        html = self.client.get('/negozio').get_data(as_text=True)
        self.assertEqual(html.count('A PREVENTIVO'), 13)
        self.assertNotIn('120,00', html)
        self.assertNotIn('/acquista/software-test', html)
        self.assertNotIn('trattativa personale', html)
        self.assertNotIn('Prezzo su preventivo', html)

    def test_get_checkout_does_not_create_order(self):
        self.apply(); response = self.client.get('/acquista/marketing-di-successo')
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn('LA RAGIONERIA DEL MARGINE', html); self.assertIn('59,00', html)
        self.assertEqual(self.Order.query.count(), 1)

    def test_checkout_total_uses_new_price(self):
        self.apply()
        response = self.client.post('/acquista/marketing-di-successo', data={
            'quantita': '2', 'nome': 'Persona Test', 'email': 'test@example.invalid',
            'indirizzo': 'Via inventata 1', 'citta': 'Citta Test'})
        self.assertEqual(response.status_code, 302)
        ordine = self.Order.query.order_by(self.Order.id.desc()).first()
        self.assertEqual(ordine.totale_cent, 12300)
        self.assertEqual(ordine.prodotto_id, 1)

    def test_all_software_cards_preserved(self):
        old = (ROOT / 'templates/shop.html').read_text()
        new = (ROOT / 'templates/_negozio_software.html').read_text()
        import re
        self.assertEqual(re.findall(r'<h2>(Master[^<]+)</h2>', old), re.findall(r'<h2>(Master[^<]+)</h2>', new))


if __name__ == '__main__': unittest.main()
