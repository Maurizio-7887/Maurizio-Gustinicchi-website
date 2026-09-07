import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import date, timedelta
from pathlib import Path

TEST_DB = Path(tempfile.gettempdir()) / 'mg_website_editorial_tests.db'
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ['DATABASE_URL'] = f'sqlite:///{TEST_DB}'
os.environ['WEBSITE_ARTICLE_PUBLISH_API_KEY'] = 'test-editorial-secret'
os.environ['SITE_URL'] = 'https://example.test'
os.environ['SECRET_KEY'] = 'test-secret'

import app as website
from app import app
from models import Articolo, db


class EditorialArticleApiTests(unittest.TestCase):
    def setUp(self):
        self.client = app.test_client()
        with app.app_context():
            Articolo.query.filter(Articolo.external_id.isnot(None)).delete()
            Articolo.query.filter(Articolo.slug.like('future-editorial-%')).delete()
            Articolo.query.filter(Articolo.slug.in_([
                'controllo-di-gestione-nelle-pmi', 'bozza-placeholder'
            ])).delete(synchronize_session=False)
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

    def _admin_session(self):
        with self.client.session_transaction() as session:
            session['admin'] = True
            session['_admin_csrf_token'] = 'csrf-test'

    @patch.object(website, 'generate_article_draft_ai')
    @patch.object(website, 'generate_article_cover_ai')
    def test_admin_ai_draft_cover_review_and_publish(self, cover_mock, draft_mock):
        self._admin_session()
        long_body = '<article><h2>Metodo operativo</h2><p>' + ('Contenuto concreto per le PMI. ' * 50) + '</p></article>'
        draft_mock.return_value = {
            'title': 'Controllo di gestione nelle PMI',
            'meta_description': 'Una guida concreta al controllo di gestione per PMI.',
            'excerpt': 'Metodo e strumenti per decidere meglio.',
            'body_html': long_body,
            'image_prompt': 'Dashboard direzionale elegante in una PMI italiana',
        }
        cover_mock.return_value = (b'fake-png-bytes', 'image/png')

        generated = self.client.post('/admin/api/articoli/genera-bozza', json={
            'titolo': 'Titolo provvisorio',
            'pubblico_target': 'Imprenditori PMI',
            'tono_voce': 'Professionale e concreto',
            'traccia_input': '- margini\n- flussi di cassa\n- decisioni',
        }, headers={'X-CSRF-Token': 'csrf-test'})
        self.assertEqual(generated.status_code, 200)
        article_id = generated.json['article_id']

        cover = self.client.post(f'/admin/api/articoli/{article_id}/genera-copertina',
                                 json={'image_prompt': generated.json['image_prompt']},
                                 headers={'X-CSRF-Token': 'csrf-test'})
        self.assertEqual(cover.status_code, 200)
        draft_media = self.client.get(cover.json['cover_url'].split('?')[0])
        self.assertEqual(draft_media.data, b'fake-png-bytes')
        self.assertIn('private', draft_media.headers['Cache-Control'])

        published = self.client.post(f'/admin/articolo/{article_id}', data={
            '_csrf_token': 'csrf-test', 'article_id': article_id, 'azione': 'pubblica',
            'titolo': generated.json['title'], 'slug': generated.json['slug'],
            'meta_description': generated.json['meta_description'], 'excerpt': generated.json['excerpt'],
            'body': long_body, 'cover': cover.json['cover_url'].split('?')[0],
            'image_prompt': generated.json['image_prompt'], 'traccia_input': '- margini',
            'pubblico_target': 'Imprenditori PMI', 'tono_voce': 'Professionale e concreto',
            'autore': 'Maurizio Gustinicchi', 'data_pubblicazione': date.today().isoformat(),
        })
        self.assertEqual(published.status_code, 302)
        with app.app_context():
            article = db.session.get(Articolo, article_id)
            self.assertTrue(article.pubblicato)
            self.assertEqual(article.stato, 'pubblicato')
            self.assertIsNotNone(article.published_at)
            self.assertEqual(article.cover_data, b'fake-png-bytes')
        self.assertIn(b'Controllo di gestione nelle PMI', self.client.get('/blog').data)
        public_media = self.client.get(cover.json['cover_url'].split('?')[0])
        self.assertIn('public', public_media.headers['Cache-Control'])

    def test_admin_publish_blocks_placeholders_and_requires_csrf(self):
        self._admin_session()
        with app.app_context():
            article = Articolo(slug='bozza-placeholder', titolo='Bozza', body='<p>bozza</p>',
                               cover='/static/img/foto-profilo.jpg', pubblicato=False, stato='bozza')
            db.session.add(article)
            db.session.commit()
            article_id = article.id
        without_csrf = self.client.post(f'/admin/articolo/{article_id}', data={})
        self.assertEqual(without_csrf.status_code, 400)
        blocked = self.client.post(f'/admin/articolo/{article_id}', data={
            '_csrf_token': 'csrf-test', 'azione': 'pubblica', 'titolo': 'Articolo [inserire data]',
            'slug': 'bozza-placeholder', 'body': '<p>' + ('Testo completo. ' * 100) + '</p>',
            'cover': '/static/img/foto-profilo.jpg', 'data_pubblicazione': date.today().isoformat(),
        })
        self.assertEqual(blocked.status_code, 400)
        with app.app_context():
            self.assertFalse(db.session.get(Articolo, article_id).pubblicato)

    def test_admin_rejects_unsafe_cover_and_css_markup(self):
        self._admin_session()
        common = {
            '_csrf_token': 'csrf-test', 'azione': 'bozza', 'titolo': 'Bozza sicura',
            'slug': 'bozza-sicura', 'body': '<p>Contenuto sicuro</p>',
            'data_pubblicazione': date.today().isoformat(),
        }
        unsafe_cover = self.client.post('/admin/articolo/nuovo', data={
            **common, 'cover': 'javascript:alert(1)'
        })
        self.assertEqual(unsafe_cover.status_code, 400)
        unsafe_css = self.client.post('/admin/articolo/nuovo', data={
            **common, 'cover': '/static/img/foto-profilo.jpg',
            'styles': '</style><script>alert(1)</script>'
        })
        self.assertEqual(unsafe_css.status_code, 400)


if __name__ == '__main__':
    unittest.main()
