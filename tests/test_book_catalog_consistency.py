"""Isolated contract tests. No app import, startup jobs, real DB or external calls.

Run: python -m pytest tests/test_book_catalog_consistency.py
Requires pytest, Flask, Flask-SQLAlchemy, beautifulsoup4.
"""
import ast
import importlib.util
import socket
import sys
import types
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock

import pytest
from bs4 import BeautifulSoup
from flask import Flask, abort, flash, redirect, render_template, request, url_for
from flask_sqlalchemy import SQLAlchemy

ROOT = Path(__file__).resolve().parents[1]


def definitions(path, names):
    tree = ast.parse(path.read_text())
    nodes = [n for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef)) and n.name in names]
    assert {n.name for n in nodes} == set(names)
    return compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec')


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', Mock(side_effect=AssertionError('Network disabled')))
    app = Flask(__name__, template_folder=str(ROOT/'templates'))
    app.config.update(TESTING=True, SECRET_KEY='synthetic-only', SQLALCHEMY_DATABASE_URI='sqlite:///:memory:')
    db = SQLAlchemy(app)
    ns = dict(db=db, datetime=datetime)
    exec(definitions(ROOT/'models.py', ['Prodotto', 'Ordine']), ns)
    spec = importlib.util.spec_from_file_location('catalog_fixture', ROOT/'catalogo_libri.py')
    catalog = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(catalog)
    ns.update(app=app, request=request, render_template=render_template, redirect=redirect,
              url_for=url_for, flash=flash, abort=abort, PAGINE=['libri'], STRIPE_SECRET_KEY='',
              SITE_URL='https://example.invalid', copertina_prodotto=catalog.copertina_prodotto,
              threading=types.SimpleNamespace(Thread=Mock()), invia_ordine_al_crm=Mock())
    exec(definitions(ROOT/'app.py', ['pagina_statica', 'negozio', 'acquista']), ns)
    app.add_url_rule('/ordine/<int:ordine_id>/<esito>', 'ordine_esito', lambda **kw: '')
    app.jinja_env.globals['copertina_prodotto'] = catalog.copertina_prodotto
    with app.app_context():
        db.create_all()
        # Fixtures derive from the catalog file; no production records are copied.
        for slug, fields in catalog.CATALOGO_LIBRI.items():
            db.session.add(ns['Prodotto'](slug=slug, tipo='libro', spedizione_cent=500, **fields))
        db.session.commit()
        yield app.test_client(), ns, catalog
        db.session.remove()
        db.drop_all()


def soup(response):
    assert response.status_code == 200
    return BeautifulSoup(response.data, 'html.parser')


def test_same_book_cards_and_checkout(env):
    client, ns, _ = env
    books = soup(client.get('/libri')).select('[data-book-slug]')
    shop = soup(client.get('/negozio')).select('[data-book-slug]')
    assert len(books) == len(shop) == 3
    for a, b in zip(books, shop):
        assert a['data-book-slug'] == b['data-book-slug']
        assert a.h2.text == b.h3.text
        assert a.img['src'] == b.img['src']
        assert a.select_one('.book-purchase-terms') == b.select_one('.book-purchase-terms')
        assert a.a['href'] == b.a['href']
        checkout = soup(client.get(a.a['href']))
        assert checkout.h1.text == a.h2.text
        assert checkout.select_one('main img')['src'] == a.img['src']
        assert checkout.select_one('.book-purchase-terms') == a.select_one('.book-purchase-terms')


def test_database_changes_propagate_without_hardcoded_prices(env):
    client, ns, _ = env
    p = ns['Prodotto'].query.first()
    p.nome = 'Titolo sintetico aggiornato'
    p.prezzo_cent = 12345
    p.spedizione_cent = 750
    p.descrizione = 'Descrizione sintetica aggiornata'
    ns['db'].session.commit()
    for path in ['/libri', '/negozio', '/acquista/'+p.slug]:
        html = soup(client.get(path)).get_text()
        for text in [p.nome, '123,45', '7,50', p.descrizione]:
            assert text in html


def test_inactive_books_not_advertised(env):
    client, ns, _ = env
    p = ns['Prodotto'].query.first()
    p.attivo = False
    ns['db'].session.commit()
    for path in ['/libri', '/negozio']:
        assert len(soup(client.get(path)).select('[data-book-slug]')) == 2
    assert client.get('/acquista/'+p.slug).status_code == 404


def test_empty_catalog_has_no_stale_purchase_links(env):
    client, ns, _ = env
    ns['Prodotto'].query.update({'attivo': False})
    ns['db'].session.commit()
    for path in ['/libri', '/negozio']:
        page = soup(client.get(path))
        assert not page.select('[data-book-slug]')
        assert 'non sono attualmente disponibili' in page.get_text()


def test_legacy_cover_is_shared_without_writing_database(env):
    client, ns, catalog = env
    p = ns['Prodotto'].query.filter_by(slug='marketing-di-successo').one()
    legacy = '/static/img/libro-marketing-successo.jpg'
    p.immagine = legacy
    ns['db'].session.commit()
    for path in ['/libri', '/negozio', '/acquista/'+p.slug]:
        page = soup(client.get(path))
        assert page.select_one('img[src="'+catalog.CATALOGO_LIBRI[p.slug]['immagine']+'"]')
        assert not page.select_one('img[src="'+legacy+'"]')
    ns['db'].session.expire_all()
    assert p.immagine == legacy


def test_custom_cover_not_overridden(env):
    client, ns, _ = env
    p = ns['Prodotto'].query.first()
    p.immagine = '/static/img/custom-fixture.jpg'
    ns['db'].session.commit()
    for path in ['/libri', '/negozio', '/acquista/'+p.slug]:
        assert soup(client.get(path)).select_one('img[src="'+p.immagine+'"]')


def test_free_shipping_consistent(env):
    client, ns, _ = env
    p = ns['Prodotto'].query.first()
    p.spedizione_cent = 0
    ns['db'].session.commit()
    for path in ['/libri', '/negozio', '/acquista/'+p.slug]:
        assert 'Spedizione inclusa' in soup(client.get(path)).get_text()


@pytest.mark.parametrize('qty', [1, 2, 20])
@pytest.mark.parametrize('card', [False, True])
def test_real_route_shipping_once_in_fake_orders(env, monkeypatch, qty, card):
    client, ns, _ = env
    stripe_create = Mock(return_value=types.SimpleNamespace(id='fixture', url='https://example.invalid/pay'))
    monkeypatch.setitem(sys.modules, 'stripe', types.SimpleNamespace(checkout=types.SimpleNamespace(Session=types.SimpleNamespace(create=stripe_create))))
    ns['STRIPE_SECRET_KEY'] = 'synthetic-test-only' if card else ''
    p = ns['Prodotto'].query.first()
    data = dict(quantita=str(qty), nome='Cliente Fittizio', email='fixture@example.invalid', indirizzo='Via Test 1', citta='Test')
    response = client.post('/acquista/'+p.slug, data=data)
    assert response.status_code in [302, 303]
    o = ns['Ordine'].query.one()
    assert o.totale_cent == p.prezzo_cent * qty + p.spedizione_cent
    if card:
        lines = stripe_create.call_args.kwargs['line_items']
        assert lines[0]['quantity'] == qty and lines[1]['quantity'] == 1
        assert lines[1]['price_data']['unit_amount'] == p.spedizione_cent
    else:
        stripe_create.assert_not_called()


@pytest.mark.parametrize('card', [False, True])
def test_payment_instructions_match_actual_branch(env, card):
    client, ns, _ = env
    ns['STRIPE_SECRET_KEY'] = 'synthetic' if card else ''
    p = ns['Prodotto'].query.first()
    text = soup(client.get('/acquista/'+p.slug)).get_text()
    assert ('Procedi al pagamento con carta' in text) == card
    assert ('Invia ordine con bonifico' in text) == (not card)


def test_get_pages_do_not_modify_products_or_orders(env):
    client, ns, _ = env
    p = ns['Prodotto'].query.first()
    before = [(p.id, p.nome, p.prezzo_cent) for p in ns['Prodotto'].query.all()]
    for path in ['/libri', '/negozio', '/acquista/'+p.slug]:
        soup(client.get(path))
    assert ns['Ordine'].query.count() == 0
    assert before == [(p.id, p.nome, p.prezzo_cent) for p in ns['Prodotto'].query.all()]
