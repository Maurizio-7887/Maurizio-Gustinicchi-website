"""Misura della crescita: ingressi per canale, crawler AI, provenienza dei lead."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_DB = Path(tempfile.gettempdir()) / 'mg_website_provenienza_tests.db'
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['SECRET_KEY'] = 'test-secret'

import app as website
from app import app
from models import VisitaCanale, VisitaCrawler, db
import provenienza


class ProvenienzaTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            VisitaCanale.query.delete()
            VisitaCrawler.query.delete()
            db.session.commit()

    def _conteggi(self):
        with app.app_context():
            return ({(v.canale, v.pagina): v.visite for v in VisitaCanale.query.all()},
                    {c.bot: c.visite for c in VisitaCrawler.query.all()})

    def test_ingressi_per_canale_e_crawler(self):
        browser = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0) Chrome/120'}
        self.client.get('/', headers={**browser, 'Referer': 'https://www.google.it/'})
        self.client.get('/', headers={**browser, 'Referer': 'https://www.google.com/'})
        self.client.get('/servizi?utm_source=chatgpt.com', headers=browser)
        self.client.get('/servizi', headers={**browser, 'Referer': 'https://www.mauriziogustinicchiconsulting.it/'})
        self.client.get('/', headers={'User-Agent': 'Mozilla/5.0 (compatible; GPTBot/1.2)'})
        self.client.get('/static/css/style.css', headers=browser)
        visite, crawler = self._conteggi()
        self.assertEqual(visite[('google_organico', '/')], 2)
        self.assertEqual(visite[('assistenti_ai', '/servizi')], 1)
        self.assertEqual(sum(visite.values()), 3)  # la navigazione interna non conta
        self.assertEqual(crawler, {'GPTBot (OpenAI)': 1})

    def test_api_protetta(self):
        with patch.object(website, 'CRM_API_KEY', 'chiave'):
            self.assertEqual(self.client.get('/api/statistiche-visite').status_code, 403)
            self.client.get('/', headers={'User-Agent': 'Mozilla/5.0 Chrome', 'Referer': 'https://www.bing.com/'})
            d = self.client.get('/api/statistiche-visite', headers={'X-API-Key': 'chiave'}).get_json()
        self.assertTrue(d['ok'])
        self.assertEqual(d['visite'][0]['canale'], 'bing_altri_motori')

    def test_provenienza_del_modulo(self):
        from werkzeug.datastructures import MultiDict
        p = website.provenienza_dal_modulo(MultiDict({'ingresso_referrer': 'https://www.perplexity.ai/search?q=x',
                                                      'ingresso_pagina': '/servizi/controllo'}))
        self.assertEqual(p, {'canale': 'assistenti_ai', 'pagina_ingresso': '/servizi/controllo',
                             'referrer_dominio': 'www.perplexity.ai'})
        self.assertEqual(provenienza.canale('https://gemini.google.com/app'), 'assistenti_ai')
        self.assertEqual(provenienza.canale('', 'youtube', 'social'), 'social')


if __name__ == '__main__':
    unittest.main()
