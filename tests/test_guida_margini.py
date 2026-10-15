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


def token_vecchio():
    from datetime import datetime
    return website._serializer_moduli().dumps(int(datetime.now().timestamp()) - 30)


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
                'privacy': '1', 'utm_source': 'facebook', 'form_token': token_vecchio()})
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
        r = self.client.post('/guida-margini', data={'nome': 'M', 'email': 'm@a.it', 'azienda': 'A',
                                                     'form_token': token_vecchio()})
        self.assertNotIn('Scarica la guida (PDF)', r.get_data(as_text=True))
        r = self.client.post('/guida-margini', data={'nome': 'M', 'email': 'm@a.it', 'privacy': '1',
                                                     'form_token': token_vecchio()})
        self.assertIn('Compila nome, email e azienda', r.get_data(as_text=True))

    def test_bot_non_crea_lead(self):
        with patch.object(website, 'invia_lead_al_crm') as crm:
            self.client.post('/guida-margini', data={'nome': 'B', 'email': 'b@b.it', 'azienda': 'B',
                                                     'privacy': '1', 'sito_web': 'http://spam'})
            crm.assert_not_called()
        with app.app_context():
            self.assertEqual(Lead.query.count(), 0)


class ContattiSpamTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            Lead.query.delete()
            db.session.commit()

    def invia(self, **campi):
        dati = {'nome': 'Mario Rossi', 'email': 'mario@ditta.it', 'azienda': 'Ditta',
                'messaggio': 'Buongiorno, vorrei un preventivo per il controllo di gestione.',
                'form_token': token_vecchio()}
        dati.update(campi)
        with patch.object(website, 'invia_lead_al_crm') as crm, patch.object(website, 'invia_email_notifica_lead') as mail:
            self.client.post('/contatti', data=dati)
            return crm.called or mail.called

    def test_contatto_vero_passa(self):
        self.assertTrue(self.invia())
        self.assertIn('form_token', self.client.get('/contatti').get_data(as_text=True))

    def test_spam_bloccato_senza_email_ne_crm(self):
        self.assertFalse(self.invia(messaggio='Hi, we can help your business rank on the first page of Google with SEO.'))
        self.assertFalse(self.invia(sito_web='http://bot'))
        self.assertFalse(self.invia(form_token=''))
        self.assertFalse(self.invia(form_token=website.form_token()))  # inviato in meno di 3 secondi
        with app.app_context():
            self.assertEqual(Lead.query.count(), 0)


if __name__ == '__main__':
    unittest.main()
