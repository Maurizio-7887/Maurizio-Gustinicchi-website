import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / 'mg_website_feed_tests.db'
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['SITE_URL'] = 'https://example.test'
os.environ['SECRET_KEY'] = 'test-secret'

from app import app
from models import Articolo, db


class ArticoliFeedTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app.app_context():
            db.create_all()
            Articolo.query.filter(Articolo.slug.like('feed-%')).delete(synchronize_session=False)
            oggi = date.today()
            db.session.add_all([
                Articolo(slug='feed-pubblicato', titolo='Pubblicato', body='<p>x</p>',
                         excerpt='Riassunto', cover='/static/img/c.png',
                         data_pubblicazione=oggi, pubblicato=True),
                Articolo(slug='feed-bozza', titolo='Bozza', body='<p>x</p>',
                         data_pubblicazione=oggi, pubblicato=False),
                Articolo(slug='feed-futuro', titolo='Futuro', body='<p>x</p>',
                         data_pubblicazione=oggi + timedelta(days=3), pubblicato=True),
            ])
            db.session.commit()

    def test_feed_espone_solo_articoli_visibili(self):
        r = self.client.get('/api/articoli.json?limit=200')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        slugs = {a['slug'] for a in data['articoli']}
        self.assertIn('feed-pubblicato', slugs)
        self.assertNotIn('feed-bozza', slugs)
        self.assertNotIn('feed-futuro', slugs)
        art = next(a for a in data['articoli'] if a['slug'] == 'feed-pubblicato')
        self.assertEqual(art['url'], 'https://example.test/blog/feed-pubblicato')
        self.assertEqual(art['cover_url'], 'https://example.test/static/img/c.png')
        self.assertNotIn('body', art)



class SeguimiTests(unittest.TestCase):
    def test_box_seguimi_sotto_articolo(self):
        os.environ['SOCIAL_FACEBOOK_URL'] = 'https://www.facebook.com/mgc'
        os.environ['SOCIAL_INSTAGRAM_URL'] = 'https://www.instagram.com/mgc/'
        try:
            with app.app_context():
                db.create_all()
                if not Articolo.query.filter_by(slug='feed-seguimi').first():
                    db.session.add(Articolo(slug='feed-seguimi', titolo='S', body='<p>x</p>',
                                            data_pubblicazione=date.today(), pubblicato=True))
                    db.session.commit()
            html = app.test_client().get('/blog/feed-seguimi').get_data(as_text=True)
            self.assertIn('Seguimi su Facebook', html)
            self.assertIn('https://www.instagram.com/mgc/', html)
        finally:
            os.environ.pop('SOCIAL_FACEBOOK_URL', None)
            os.environ.pop('SOCIAL_INSTAGRAM_URL', None)

    def test_url_crm_ricavato_dal_webhook(self):
        import app as website
        vecchio = website.CRM_WEBHOOK_URL
        website.CRM_WEBHOOK_URL = 'https://crm.example.test/api/webhook/lead_sito'
        try:
            self.assertEqual(website._crm_social_links_url(), 'https://crm.example.test/api/public/social-links')
        finally:
            website.CRM_WEBHOOK_URL = vecchio


if __name__ == '__main__':
    unittest.main()
