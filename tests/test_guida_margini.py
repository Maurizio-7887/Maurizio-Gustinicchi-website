import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

TEST_DB = Path(tempfile.gettempdir()) / 'mg_website_guida_tests.db'
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['SITE_URL'] = 'https://example.test'
os.environ['SECRET_KEY'] = 'test-secret'

import app as website
from app import app
from models import Lead, db


class GuidaMarginiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            Lead.query.delete()
            db.session.commit()

    def test_pagina_e_pdf_esistono(self):
        r = self.client.get('/guida-margini?utm_source=facebook&utm_campaign=guida')
        html = r.get_data(as_text=True)
        self.assertEqual(r.status_code, 200)
        self.assertIn('5 segnali che il margine', html)
        self.assertIn('name="utm_source" value="facebook"', html)
        self.assertTrue(Path(website.app.static_folder, 'docs', 'guida-5-segnali-margine.pdf').exists())

    def test_download_invia_lead_al_crm_con_consenso(self):
        inviati = []
        with patch.object(website, 'invia_lead_al_crm', side_effect=inviati.append), \
             patch.object(website, 'invia_email_notifica_lead'):
            r = self.client.post('/guida-margini', data={
                'nome': 'Mario Rossi', 'email': 'mario@azienda.it', 'azienda': 'Azienda Srl',
                'privacy': '1', 'utm_source': 'facebook'})
            html = r.get_data(as_text=True)
            self.assertIn('Scarica la guida (PDF)', html)
            self.assertIn('/static/docs/guida-5-segnali-margine.pdf', html)
            import time
            for _ in range(50):
                if inviati:
                    break
                time.sleep(0.02)
        self.assertEqual(len(inviati), 1)
        p = inviati[0]
        self.assertFalse(p['consenso_newsletter'])
        self.assertEqual(p['tipo_anagrafica'], 'Lead')
        self.assertEqual(p['utm'], {'utm_source': 'facebook'})
        with app.app_context():
            self.assertEqual(Lead.query.filter_by(fonte='guida_margini').count(), 1)

    def test_senza_privacy_o_azienda_niente_download(self):
        r = self.client.post('/guida-margini', data={'nome': 'M', 'email': 'm@a.it', 'azienda': 'A'})
        self.assertNotIn('Scarica la guida (PDF)', r.get_data(as_text=True))
        r = self.client.post('/guida-margini', data={'nome': 'M', 'email': 'm@a.it', 'privacy': '1'})
        self.assertIn('Compila nome, email e azienda', r.get_data(as_text=True))

    def test_bot_non_crea_lead(self):
        with patch.object(website, 'invia_lead_al_crm') as crm:
            self.client.post('/guida-margini', data={'nome': 'B', 'email': 'b@b.it', 'azienda': 'B',
                                                     'privacy': '1', 'sito_web': 'http://spam'})
            crm.assert_not_called()
        with app.app_context():
            self.assertEqual(Lead.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
