import os
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / 'mg_website_editorial_tests.db'
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['WEBSITE_ARTICLE_PUBLISH_API_KEY'] = 'test-editorial-secret'
os.environ['SITE_URL'] = 'https://example.test'
os.environ['SECRET_KEY'] = 'test-secret'

from app import app
from models import Articolo, db


class EditorialArticleApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app.app_context():
            Articolo.query.filter(Articolo.external_id.isnot(None)).delete()
            Articolo.query.filter(Articolo.slug.like('future-editorial-%')).delete()
            db.session.commit()
        self.external_id = '5108b5b3-f3be-4db2-8e9c-17a4c7332a76'

    def payload(self, **overrides):
        payload = {
            'version': 1,
            'slug': 'editorial-api-test',
            'title': 'Titolo articolo editoriale',
            'meta_description': 'Descrizione per test editoriale.',
            'excerpt': 'Estratto per la card del blog.',
            'body_html': '<article><h1>Test</h1><p>Corpo sicuro.</p><script>alert(1)</script></article>',
            'status': 'published',
            'publish_date': date.today().isoformat(),
            'cover': '/static/img/copertina.jpg',
        }
        payload.update(overrides)
        return payload

    def put(self, payload, external_id=None, key='test-editorial-secret'):
        return self.client.put(
            f'/api/internal/articles/{external_id or self.external_id}',
            json=payload,
            headers={'X-API-Key': key},
        )

    def test_requires_key_and_validates_payload(self):
        self.assertEqual(self.put(self.payload(), key='wrong').status_code, 401)
        invalid = self.payload(slug='Maiuscolo non valido')
        self.assertEqual(self.put(invalid).status_code, 400)
        unsafe_cover = self.payload(cover='javascript:alert(1)')
        self.assertEqual(self.put(unsafe_cover).status_code, 400)

    def test_create_replay_conflict_and_update_are_idempotent(self):
        created = self.put(self.payload())
        self.assertEqual(created.status_code, 201)
        self.assertTrue(created.json['ok'])
        self.assertEqual(created.json['url'], 'https://example.test/blog/editorial-api-test')

        replay = self.put(self.payload())
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json['id'], created.json['id'])

        conflict = self.put(self.payload(title='Contenuto diverso'))
        self.assertEqual(conflict.status_code, 409)

        updated = self.put(self.payload(version=2, title='Versione aggiornata'))
        self.assertEqual(updated.status_code, 200)
        with app.app_context():
            article = Articolo.query.filter_by(external_id=self.external_id).one()
            self.assertEqual(article.version, 2)
            self.assertNotIn('<script>', article.body)

    def test_future_articles_are_hidden_and_cover_urls_are_absolute(self):
        future = Articolo(
            slug='future-editorial-hidden', titolo='Futuro editoriale nascosto',
            meta_description='', excerpt='', cover='/static/img/future.jpg', body='<p>future</p>',
            data_pubblicazione=date.today() + timedelta(days=1), pubblicato=True,
        )
        with app.app_context():
            db.session.add(future)
            db.session.commit()

        self.assertNotIn(b'Futuro editoriale nascosto', self.client.get('/blog').data)
        self.assertEqual(self.client.get('/blog/future-editorial-hidden').status_code, 404)
        self.assertNotIn(b'future-editorial-hidden', self.client.get('/sitemap.xml').data)

        self.assertEqual(self.put(self.payload()).status_code, 201)
        blog = self.client.get('/blog')
        self.assertIn(b'https://example.test/static/img/copertina.jpg', blog.data)
        detail = self.client.get('/blog/editorial-api-test')
        self.assertIn(b'https://example.test/static/img/copertina.jpg', detail.data)


if __name__ == '__main__':
    unittest.main()
