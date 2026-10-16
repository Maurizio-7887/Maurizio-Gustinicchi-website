# -*- coding: utf-8 -*-
"""Da dove arrivano i visitatori del sito (SEO, AEO, social, email...).

Classificazione del canale dal referrer e dagli UTM, riconoscimento dei
crawler. Nessun dato personale: si contano solo gli ingressi aggregati."""
import re
from urllib.parse import urlparse

DOMINIO_SITO = 'mauriziogustinicchiconsulting.it'

# Assistenti AI (AEO): chi clicca un link citato in una risposta.
_ASSISTENTI_AI = ('chatgpt.com', 'chat.openai.com', 'openai.com', 'perplexity.ai', 'gemini.google.com',
                  'bard.google.com', 'copilot.microsoft.com', 'claude.ai', 'you.com', 'phind.com',
                  'meta.ai', 'mistral.ai', 'chat.mistral.ai', 'deepseek.com', 'grok.com', 'x.ai')
_MOTORI = {'google': 'google_organico', 'bing': 'bing_altri_motori', 'duckduckgo': 'bing_altri_motori',
           'yahoo': 'bing_altri_motori', 'ecosia': 'bing_altri_motori', 'qwant': 'bing_altri_motori',
           'yandex': 'bing_altri_motori', 'baidu': 'bing_altri_motori', 'startpage': 'bing_altri_motori'}
_SOCIAL = ('facebook.com', 'fb.com', 'instagram.com', 'linkedin.com', 'lnkd.in', 't.co', 'twitter.com',
           'x.com', 'youtube.com', 'tiktok.com', 'whatsapp.com', 'wa.me', 'pinterest.')
_EMAIL = ('mail.google.com', 'outlook.live.com', 'outlook.office', 'mail.yahoo', 'webmail', 'mailchi.mp',
          'list-manage.com', 'libero.it', 'aruba.it')

CANALI = {
    'google_organico': 'Google (ricerca organica)',
    'bing_altri_motori': 'Bing e altri motori',
    'assistenti_ai': 'Assistenti AI (ChatGPT, Perplexity, Gemini…)',
    'social': 'Social',
    'email': 'Email e newsletter',
    'pubblicita': 'Pubblicità a pagamento',
    'altri_siti': 'Altri siti (link)',
    'diretto': 'Diretto / sconosciuto',
}

# Crawler: motori di ricerca e AI che leggono il sito.
_BOT = [
    ('GPTBot', 'GPTBot (OpenAI)'), ('OAI-SearchBot', 'OAI-SearchBot (ChatGPT ricerca)'),
    ('ChatGPT-User', 'ChatGPT-User'), ('ClaudeBot', 'ClaudeBot (Anthropic)'), ('Claude-User', 'Claude-User'),
    ('Claude-SearchBot', 'Claude-SearchBot'), ('PerplexityBot', 'PerplexityBot'),
    ('Perplexity-User', 'Perplexity-User'), ('Google-Extended', 'Google-Extended (Gemini)'),
    ('Applebot', 'Applebot'), ('CCBot', 'CCBot (Common Crawl)'), ('Bytespider', 'Bytespider'),
    ('meta-externalagent', 'Meta AI'), ('Amazonbot', 'Amazonbot'), ('DuckAssistBot', 'DuckAssistBot'),
    ('Googlebot', 'Googlebot'), ('bingbot', 'Bingbot'), ('YandexBot', 'YandexBot'),
]
BOT_AI = {'GPTBot (OpenAI)', 'OAI-SearchBot (ChatGPT ricerca)', 'ChatGPT-User', 'ClaudeBot (Anthropic)',
          'Claude-User', 'Claude-SearchBot', 'PerplexityBot', 'Perplexity-User', 'Google-Extended (Gemini)',
          'CCBot (Common Crawl)', 'Bytespider', 'Meta AI', 'Amazonbot', 'DuckAssistBot', 'Applebot'}
_BOT_GENERICO = re.compile(r'bot|crawl|spider|slurp|preview|fetch|monitor|python-requests|curl|wget|httpx|'
                           r'headless|lighthouse|semrush|ahrefs|mj12|dotbot|petal', re.I)


def bot_da_user_agent(ua):
    """Nome del crawler noto, 'altro_bot' per i bot generici, None per i browser."""
    ua = ua or ''
    for chiave, nome in _BOT:
        if chiave.lower() in ua.lower():
            return nome
    return 'altro_bot' if _BOT_GENERICO.search(ua) or not ua.strip() else None


def _host(url):
    try:
        return (urlparse(url or '').hostname or '').lower()
    except ValueError:
        return ''


def e_interno(referrer):
    h = _host(referrer)
    return bool(h) and (h == DOMINIO_SITO or h.endswith('.' + DOMINIO_SITO) or h.endswith('.up.railway.app'))


def canale(referrer='', utm_source='', utm_medium='', gclid=''):
    """Canale di provenienza di un ingresso."""
    sorgente, mezzo = (utm_source or '').lower(), (utm_medium or '').lower()
    if gclid or mezzo in ('cpc', 'ppc', 'paid', 'paid_social', 'ads') or 'ads' in sorgente:
        return 'pubblicita'
    if re.search(r'chatgpt|openai|perplexity|gemini|copilot|claude|mistral|deepseek', sorgente):
        return 'assistenti_ai'
    if mezzo in ('email', 'e-mail', 'newsletter') or sorgente in ('mailchimp', 'newsletter', 'crm'):
        return 'email'
    if mezzo in ('social', 'social-network', 'organic_social') or sorgente in ('facebook', 'instagram',
                                                                                'linkedin', 'fb', 'ig'):
        return 'social'
    h = _host(referrer)
    if not h:
        return 'diretto'
    if any(h == a or h.endswith('.' + a) for a in _ASSISTENTI_AI):
        return 'assistenti_ai'
    if h.startswith('www.google.') or h.startswith('google.') or re.match(r'^(www\.)?google\.[a-z.]+$', h):
        return 'google_organico'
    for nome, can in _MOTORI.items():
        if re.search(r'(^|\.)' + nome + r'\.', h):
            return can
    if any(s in h for s in _SOCIAL):
        return 'social'
    if any(s in h for s in _EMAIL):
        return 'email'
    return 'altri_siti'
