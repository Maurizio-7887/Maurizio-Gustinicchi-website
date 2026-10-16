"""SEO servizi: rendering e route reali estratti senza importare app o aprire DB.

Esecuzione: python -m unittest discover -s tests -p test_service_seo.py -v
Richiede Flask. Non avvia l'applicazione completa, migrazioni o servizi esterni.
"""
import ast
import re
import unittest
from datetime import date
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
import xml.etree.ElementTree as ET

from flask import Flask, Response, abort, redirect, render_template, url_for

ROOT = Path(__file__).resolve().parents[1]
ORIGIN = 'https://www.mauriziogustinicchiconsulting.it'
SLUGS = ('controllo', 'cfo-esterno', 'software-gestionali-su-misura')


class Document(HTMLParser):
    def __init__(self, text):
        super().__init__()
        self.tags = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def attrs(self, tag):
        return [attrs for name, attrs in self.tags if name == tag]


class EmptyQuery:
    """Sitemap: nessun articolo/landing, nessuna connessione al database."""
    def filter_by(self, **kwargs):
        return self

    def filter(self, *args):
        return self

    def all(self):
        return []


class PublicationDate:
    def __le__(self, other):
        return True


def isolated_app():
    app = Flask(__name__, template_folder=str(ROOT / 'templates'),
                static_folder=str(ROOT / 'static'))
    app.config.update(TESTING=True, SECRET_KEY='isolated-seo-test')
    app.jinja_env.globals['current_year'] = date.today().year
    app.jinja_env.globals['social_links'] = lambda: {'facebook': '', 'instagram': ''}
    scope = dict(app=app, render_template=render_template, abort=abort,
                 redirect=redirect, url_for=url_for, Response=Response,
                 SITE_URL=ORIGIN, date=date,
                 Articolo=SimpleNamespace(query=EmptyQuery(), data_pubblicazione=PublicationDate()),
                 LandingPage=SimpleNamespace(query=EmptyQuery()))
    source = ast.parse((ROOT / 'app.py').read_text())
    functions = {'index', 'pagina_statica', 'servizio_dettaglio', 'r_servizio', 'sitemap'}
    nodes = [n for n in source.body if
             (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and
              t.id in {'PAGINE', 'SERVIZI_DETTAGLIO'} for t in n.targets)) or
             (isinstance(n, ast.FunctionDef) and n.name in functions)]
    exec(compile(ast.Module(body=nodes, type_ignores=[]), 'isolated-routes', 'exec'), scope)
    return app, scope


class ServiceSeoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.scope = isolated_app()
        cls.client = cls.app.test_client()

    def page(self, path):
        response = self.client.get(path)
        self.assertEqual(response.status_code, 200, path)
        return response.get_data(as_text=True)

    def test_service_allowlist(self):
        for slug in SLUGS:
            self.assertIn(slug, self.scope['SERVIZI_DETTAGLIO'])

    def test_pages_render_with_one_h1(self):
        for slug in SLUGS:
            with self.subTest(slug=slug):
                self.assertEqual(len(Document(self.page('/servizi/' + slug)).attrs('h1')), 1)

    def test_unique_titles_and_descriptions(self):
        titles, descriptions = [], []
        for slug in SLUGS:
            text = self.page('/servizi/' + slug)
            title = re.search(r'<title>(.*?)</title>', text, re.S).group(1).strip()
            description = next(a['content'] for a in Document(text).attrs('meta')
                               if a.get('name') == 'description')
            self.assertGreater(len(title), 20)
            self.assertLessEqual(len(title), 65)
            self.assertGreaterEqual(len(description), 90)
            self.assertLessEqual(len(description), 165)
            titles.append(title)
            descriptions.append(description)
        self.assertEqual(len(set(titles)), 3)
        self.assertEqual(len(set(descriptions)), 3)

    def test_canonical_and_social_metadata(self):
        for slug in SLUGS:
            path = '/servizi/' + slug
            doc = Document(self.page(path + '?utm_source=test'))
            self.assertEqual([a['href'] for a in doc.attrs('link') if a.get('rel') == 'canonical'], [ORIGIN + path])
            metas = doc.attrs('meta')
            desc = next(a['content'] for a in metas if a.get('name') == 'description')
            self.assertEqual(next(a['content'] for a in metas if a.get('property') == 'og:description'), desc)
            self.assertFalse(any(a.get('name') == 'robots' and 'noindex' in a.get('content', '') for a in metas))

    def test_google_verification_preserved(self):
        for slug in SLUGS:
            self.assertIn('7Sl1WnU75VcUKkbBLe3j72OguKADmjiPH-GGrSP71_I', self.page('/servizi/' + slug))

    def test_home_and_services_link_to_destinations(self):
        for path in ('/', '/servizi'):
            links = [a.get('href') for a in Document(self.page(path)).attrs('a')]
            for slug in SLUGS:
                self.assertIn('/servizi/' + slug, links)

    def test_digitalization_links_to_software(self):
        self.assertIn('href="/servizi/software-gestionali-su-misura"', self.page('/servizi/digitalizzazione'))

    def test_lab_and_service_links_resolve(self):
        home_ids = [a.get('id') for _, a in Document(self.page('/')).tags]
        for slug in SLUGS:
            for a in Document(self.page('/servizi/' + slug)).attrs('a'):
                href = a.get('href', '')
                if href.startswith('/servizi'):
                    self.page(href)
                elif href.startswith('/#'):
                    self.assertIn(href[2:], home_ids)

    def test_sitemap_has_new_pages_once(self):
        response = self.client.get('/sitemap.xml')
        self.assertEqual(response.status_code, 200)
        root = ET.fromstring(response.data)
        urls = [n.text for n in root.findall('{*}url/{*}loc')]
        for slug in SLUGS:
            self.assertEqual(urls.count(ORIGIN + '/servizi/' + slug), 1)

    def test_invalid_or_internal_templates_are_404(self):
        for slug in ('non-esiste', '_service_layout', 'cfo-esterno.html'):
            self.assertEqual(self.client.get('/servizi/' + slug).status_code, 404)

    def test_legacy_control_url_keeps_redirect(self):
        response = self.client.get('/servizi/dettaglio-controllo.html')
        self.assertEqual(response.status_code, 301)
        self.assertEqual(response.headers['Location'], '/servizi/controllo')

    def test_control_has_no_unsubstantiated_guarantees(self):
        text = self.page('/servizi/controllo').lower()
        for phrase in ('10 milioni', 'certezza del dato', 'a prova di imprevisto', 'pari a zero'):
            self.assertNotIn(phrase, text)
        self.assertIn('non eliminano il rischio', text)

    def test_home_lab_and_schema_are_preserved(self):
        text = self.page('/')
        for element in ('simulatore-margini', 'azienda-prima-dopo', 'test-controllo-gestione'):
            self.assertIn('id="' + element + '"', text)
        self.assertIn('application/ld+json', text)
        self.assertEqual(len(Document(text).attrs('h1')), 1)

    def test_service_stylesheet_is_served(self):
        response = self.client.get('/static/css/service-pages.css')
        self.assertEqual(response.status_code, 200)
        response.close()


if __name__ == '__main__':
    unittest.main()
