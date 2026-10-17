"""Test isolati: nessun import di app.py, database, email o CRM reali.
Esecuzione: python -m unittest discover -s tests -p test_conversion_paths.py -v
Richiede Flask, già dipendenza del sito.
"""
import ast
import json
from pathlib import Path
import re
from types import SimpleNamespace
import unittest
from flask import Flask, render_template, request, flash, redirect, url_for

ROOT = Path(__file__).resolve().parents[1]

def isolated_app():
    app = Flask(__name__, template_folder=str(ROOT / 'templates'), static_folder=str(ROOT / 'static'))
    app.secret_key = 'isolated-test-only'
    app.context_processor(lambda: dict(current_year=2026, form_token=lambda: 'test-token', social_links=lambda: SimpleNamespace(facebook='', instagram='')))
    @app.get('/')
    def index(): return render_template('index.html')
    @app.get('/servizi/<slug>')
    def servizio(slug): return render_template('servizi/' + slug + '.html')
    calls = []
    class FakeLead:
        def __init__(self, **kw): self.id = 1; calls.append(('lead', kw))
    class FakeThread:
        def __init__(self, **kw): calls.append(('thread', kw['target'].__name__))
        def start(self): pass
    from datetime import datetime
    scope = dict(app=app, request=request, render_template=render_template, flash=flash, redirect=redirect, url_for=url_for,
                 motivo_spam_modulo=lambda f: bool(f.get('sito_web')), Lead=FakeLead,
                 db=SimpleNamespace(session=SimpleNamespace(add=lambda x: None, commit=lambda: calls.append(('commit',)))),
                 provenienza_dal_modulo=lambda f: {}, datetime=datetime, threading=SimpleNamespace(Thread=FakeThread),
                 invia_lead_al_crm=lambda p: None, invia_email_notifica_lead=lambda p: None)
    # Compile only the existing contact handler. Never execute module startup code.
    source=ast.parse((ROOT/'app.py').read_text())
    fn=next(n for n in source.body if isinstance(n, ast.FunctionDef) and n.name=='contatti')
    exec(compile(ast.Module(body=[fn], type_ignores=[]), 'isolated-contact', 'exec'), scope)
    return app, calls

class ConversionPathsTest(unittest.TestCase):
    def setUp(self): self.app,self.calls=isolated_app(); self.client=self.app.test_client()
    def html(self,path='/'): return self.client.get(path).get_data(as_text=True)
    def test_home_one_h1(self): self.assertEqual(len(re.findall(r'<h1[ >]',self.html())),1)
    def test_search_verification_preserved(self): self.assertIn('7Sl1WnU75VcUKkbBLe3j72OguKADmjiPH-GGrSP71_I',self.html())
    def test_structured_data_parses(self):
        blocks=re.findall(r'<script type="application/ld\+json">(.*?)</script>',self.html(),re.S)
        self.assertEqual(len(blocks),2)
        for b in blocks: json.loads(b)
    def test_faq_matches_visible_content(self):
        h=self.html(); schema=json.loads(re.findall(r'<script type="application/ld\+json">(.*?)</script>',h,re.S)[0])
        for q in schema['mainEntity']: self.assertIn(q['name'],h); self.assertIn(q['acceptedAnswer']['text'],h)
    def test_main_paths_and_tools(self):
        h=self.html()
        for slug in ['controllo','software-gestionali-su-misura','cfo-esterno']: self.assertIn('/servizi/'+slug,h)
        for id_ in ['simulatore-margini','azienda-prima-dopo','test-controllo-gestione']: self.assertIn('id="'+id_+'"',h)
    def test_navigation_resources_kept(self):
        h=self.html()
        for url in ['/formazione','/libri','/negozio','/blog','/video','/certificati','/partner','/testimonianze']: self.assertIn('href="'+url+'"',h)
        self.assertNotIn('ACQUISTA',h)
    def test_no_video_autoplay(self):
        tags=re.findall(r'<video\b[^>]*>',self.html());self.assertTrue(tags)
        for t in tags: self.assertNotIn('autoplay',t);self.assertIn('preload="none"',t)
    def test_contact_required_fields_only(self):
        h=self.html('/contatti'); fields=re.findall(r'<(?:input|textarea)\b[^>]*\brequired\b[^>]*>',h)
        self.assertEqual(sorted(re.search(r'name="([^"]+)"',f).group(1) for f in fields),['email','messaggio','nome'])
        self.assertNotIn('name="oggetto"',h)
    def test_honeypot_and_token_preserved(self):
        h=self.html('/contatti'); self.assertIn('name="form_token" value="test-token"',h);self.assertIn('name="sito_web"',h)
    def test_contact_context_whitelist(self):
        for key,label in [('software','Software gestionale su misura'),('cfo','CFO esterno'),('controllo','Controllo di gestione')]: self.assertIn(label,self.html('/contatti?servizio='+key))
        h=self.html('/contatti?servizio=%3Cscript%3Ealert(1)%3C/script%3E');self.assertNotIn('alert(1)',h)
    def test_privacy_no_forced_marketing(self):
        h=self.html('/contatti');self.assertIn('informativa sul trattamento dei dati',h);self.assertNotIn('accetti la',h);self.assertNotIn('name="consenso',h)
    def test_service_specific_contact_links(self):
        for slug,key in [('controllo','controllo'),('cfo-esterno','cfo'),('software-gestionali-su-misura','software')]:
            self.assertIn('/contatti?servizio='+key+'#richiesta',self.html('/servizi/'+slug))
    def test_synthetic_submission_stubs_only(self):
        r=self.client.post('/contatti',data=dict(nome='Persona Test',email='test@example.invalid',messaggio='Esempio sintetico di processo'))
        self.assertEqual(r.status_code,302);self.assertEqual(sum(c[0]=='lead' for c in self.calls),1);self.assertIn(('commit',),self.calls)
        self.assertEqual(sum(c[0]=='thread' for c in self.calls),2)
    def test_missing_required_not_saved(self):
        r=self.client.post('/contatti',data=dict(nome='Test'));self.assertEqual(r.status_code,302);self.assertEqual(self.calls,[])
    def test_spam_not_saved(self):
        r=self.client.post('/contatti',data=dict(nome='Test',email='test@example.invalid',messaggio='Test',sito_web='spam'))
        self.assertEqual(r.status_code,302);self.assertEqual(self.calls,[])

if __name__=='__main__': unittest.main()
