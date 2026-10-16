"""Home: un solo H1, niente Markdown visibile, FAQ e dati strutturati allineati."""
import html
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('SECRET_KEY', 'test')
import app as site  # noqa: E402


def _home():
    return site.app.test_client().get('/').get_data(as_text=True)


def test_un_solo_h1_e_niente_asterischi():
    h = _home()
    assert len(re.findall(r'<h1[\s>]', h)) == 1
    assert '**' not in re.sub(r'<script.*?</script>', '', h, flags=re.S)


def test_faq_visibili_uguali_ai_dati_strutturati():
    h = _home()
    blocchi = [json.loads(b) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]
    faq = next(b for b in blocchi if b.get('@type') == 'FAQPage')
    visibili = re.findall(r'<div class="faq-item">\s*<h3>\d+\. (.*?)</h3>\s*<p>(.*?)</p>', h, re.S)
    assert len(visibili) == len(faq['mainEntity'])
    for (q, r), e in zip(visibili, faq['mainEntity']):
        assert html.unescape(q) == e['name']
        assert html.unescape(re.sub(r'<[^>]+>', '', r)) == e['acceptedAnswer']['text']
    assert any(b.get('@graph') for b in blocchi)  # Person + ProfessionalService


def test_niente_promesse_non_documentate():
    h = _home()
    for frase in ('Leader in Italia', 'Zero Errori', '150%', 'totale fiducia', '&mdash; LIVE'):
        assert frase not in h
