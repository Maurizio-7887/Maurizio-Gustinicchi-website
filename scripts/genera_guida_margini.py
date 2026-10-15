# -*- coding: utf-8 -*-
"""Genera la guida PDF di richiamo (lead magnet) per le campagne Meta Ads:
"5 segnali che il margine della tua PMI sta scendendo".

Uso:  python scripts/genera_guida_margini.py
Output: static/docs/guida-5-segnali-margine.pdf
"""
import os

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, PageBreak, Paragraph, SimpleDocTemplate, Spacer,
                                Table, TableStyle)

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(BASE, 'static', 'docs', 'guida-5-segnali-margine.pdf')
FOTO = os.path.join(BASE, 'static', 'img', 'foto-profilo.jpg')

NAVY = colors.HexColor('#0d2b4e')
RED = colors.HexColor('#e05252')
SOFT = colors.HexColor('#f3f6fa')
MUTED = colors.HexColor('#586579')
INK = colors.HexColor('#172033')

S = {
    'h1': ParagraphStyle('h1', fontName='Helvetica-Bold', fontSize=26, leading=31, textColor=colors.white),
    'sub': ParagraphStyle('sub', fontName='Helvetica', fontSize=13, leading=18, textColor=colors.HexColor('#dbe4f0')),
    'kicker': ParagraphStyle('kicker', fontName='Helvetica-Bold', fontSize=9, leading=12, textColor=RED,
                             spaceAfter=4),
    'h2': ParagraphStyle('h2', fontName='Helvetica-Bold', fontSize=17, leading=22, textColor=NAVY, spaceAfter=8),
    'h3': ParagraphStyle('h3', fontName='Helvetica-Bold', fontSize=11, leading=15, textColor=NAVY,
                         spaceBefore=8, spaceAfter=3),
    'p': ParagraphStyle('p', fontName='Helvetica', fontSize=10.5, leading=15.5, textColor=INK, spaceAfter=6),
    'small': ParagraphStyle('small', fontName='Helvetica', fontSize=8.5, leading=12, textColor=MUTED),
    'box': ParagraphStyle('box', fontName='Helvetica', fontSize=10, leading=14.5, textColor=INK),
    'formula': ParagraphStyle('formula', fontName='Helvetica-Bold', fontSize=10, leading=14, textColor=NAVY),
    'center': ParagraphStyle('center', fontName='Helvetica', fontSize=10.5, leading=15, textColor=INK,
                             alignment=TA_CENTER),
}


def riquadro(contenuto, sfondo=SOFT, bordo=None):
    t = Table([[contenuto]], colWidths=[170 * mm])
    stile = [('BACKGROUND', (0, 0), (-1, -1), sfondo), ('LEFTPADDING', (0, 0), (-1, -1), 12),
             ('RIGHTPADDING', (0, 0), (-1, -1), 12), ('TOPPADDING', (0, 0), (-1, -1), 10),
             ('BOTTOMPADDING', (0, 0), (-1, -1), 10)]
    if bordo:
        stile.append(('LINEBEFORE', (0, 0), (0, -1), 4, bordo))
    t.setStyle(TableStyle(stile))
    return t


SEGNALI = [
    {
        'titolo': 'Il fatturato cresce, ma in banca i soldi non aumentano',
        'cosa': "Chiudi l'anno con più vendite dell'anno prima, eppure il conto corrente è sempre tirato "
                "e il fido viene usato più spesso.",
        'perche': "Vendere di più non significa guadagnare di più. Se i nuovi volumi arrivano con sconti, "
                  "costi di produzione più alti o pagamenti lenti, il fatturato sale e la cassa scende.",
        'misura': 'Confronta mese per mese: variazione del fatturato <b>vs</b> variazione della liquidità '
                  'netta (cassa e banche meno debiti a breve).',
        'fare': 'Costruisci una previsione di cassa a 12 mesi con scadenzario attivo e passivo, e aggiornala '
                'ogni settimana: è anche la base per parlare con la banca.',
    },
    {
        'titolo': 'I clienti pagano sempre più tardi',
        'cosa': 'Le fatture scadute aumentano e i solleciti diventano la normalità.',
        'perche': "Ogni giorno di ritardo è un finanziamento gratuito che fai ai tuoi clienti. "
                  "Il margine c'è sulla carta, ma lo paghi in interessi e tensione di cassa.",
        'misura': 'Giorni medi di incasso (DSO) = crediti verso clienti / fatturato annuo × 365. '
                  'Guarda come si muove nel tempo, non il singolo valore.',
        'fare': 'Monitora il DSO ogni mese, per cliente: individua chi allunga i tempi e intervieni '
                'su condizioni di pagamento e solleciti prima che il ritardo diventi abitudine.',
    },
    {
        'titolo': 'Non sai quanto guadagni su ogni prodotto o commessa',
        'cosa': 'Conosci il risultato complessivo a fine anno, ma non sapresti dire quale prodotto, cliente '
                'o commessa ti fa guadagnare e quale ti fa perdere.',
        'perche': 'Un risultato medio positivo può nascondere commesse in perdita che le altre stanno '
                  'pagando. Senza questo dato, i prezzi si fanno "a sensazione".',
        'misura': 'Margine di contribuzione = ricavi − costi variabili (materiali, lavorazioni esterne, '
                  'provvigioni, ore dirette). Calcolalo per prodotto, cliente e commessa.',
        'fare': 'Classifica prodotti e clienti per margine, non per fatturato. Rivedi i listini dei casi '
                'in fondo alla classifica e verifica i costi reali con chi produce.',
    },
    {
        'titolo': 'Preventivo e consuntivo non tornano, e nessuno sa perché',
        'cosa': 'Le commesse costano più del previsto, ma la spiegazione è sempre generica: '
                '"i materiali sono aumentati", "ci abbiamo messo di più".',
        'perche': "Se uno scostamento non ha una causa e un responsabile, si ripeterà. "
                  "Il conto economico dice quanto hai perso, non chi poteva evitarlo.",
        'misura': "Analisi degli scostamenti: separa l'effetto prezzo (acquisti), l'effetto quantità "
                  "(produzione), l'effetto efficienza (reparto) e l'effetto volume (vendite).",
        'fare': 'A ogni chiusura mensile, assegna ogni scostamento significativo a una funzione aziendale '
                'e decidi un\'azione. Meglio durante il mese che a consuntivo.',
    },
    {
        'titolo': 'Il magazzino cresce più delle vendite',
        'cosa': 'Gli scaffali sono pieni, ma mancano proprio i codici che servono; le giacenze a sistema '
                'non coincidono con quelle reali.',
        'perche': 'Il magazzino è cassa ferma: scorte eccessive o obsolete assorbono liquidità e, '
                  'prima o poi, diventano svalutazioni che colpiscono il margine.',
        'misura': 'Indice di rotazione = costo del venduto / valore medio delle scorte. Affiancalo '
                  'all\'elenco degli articoli fermi da più di 6-12 mesi.',
        'fare': 'Allinea le giacenze reali con un inventario per ubicazioni, poi tieni sotto controllo '
                'riordini e articoli lenti con un gestionale di magazzino aggiornato in tempo reale.',
    },
]

CHECKLIST = [
    'So quanta cassa avrò tra 3 mesi, non solo quanta ne ho oggi.',
    'Conosco i giorni medi di incasso e so se stanno salendo.',
    'Conosco il margine di contribuzione dei miei 10 prodotti/clienti principali.',
    'Ogni scostamento importante tra preventivo e consuntivo ha un responsabile.',
    'Le giacenze a sistema coincidono con quelle reali.',
    'Ricevo i numeri chiave ogni mese, entro pochi giorni dalla chiusura.',
    'I dati arrivano da un unico sistema, non da fogli Excel sparsi.',
    "Ho un sistema che mi avvisa prima che un problema diventi crisi (art. 2086 c.c.).",
]


def pagina(canvas, doc):
    canvas.saveState()
    if doc.page > 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, A4[1] - 9 * mm, A4[0], 9 * mm, stroke=0, fill=1)
        canvas.setFillColor(colors.white)
        canvas.setFont('Helvetica-Bold', 8)
        canvas.drawString(20 * mm, A4[1] - 6 * mm, 'MAURIZIO GUSTINICCHI CONSULTING')
        canvas.drawRightString(A4[0] - 20 * mm, A4[1] - 6 * mm, '5 segnali che il margine sta scendendo')
    canvas.setFillColor(MUTED)
    canvas.setFont('Helvetica', 8)
    canvas.drawString(20 * mm, 10 * mm, 'www.mauriziogustinicchiconsulting.it  ·  info@mauriziogustinicchiconsulting.it')
    canvas.drawRightString(A4[0] - 20 * mm, 10 * mm, f'{doc.page}')
    canvas.restoreState()


def copertina(canvas, doc):
    canvas.saveState()
    canvas.setFillColor(NAVY)
    canvas.rect(0, 0, A4[0], A4[1], stroke=0, fill=1)
    canvas.setFillColor(RED)
    canvas.rect(20 * mm, A4[1] - 62 * mm, 30 * mm, 2.2 * mm, stroke=0, fill=1)
    canvas.restoreState()
    pagina_cop = doc.page
    if pagina_cop > 1:
        pagina(canvas, doc)


def costruisci():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    doc = SimpleDocTemplate(OUT, pagesize=A4, leftMargin=20 * mm, rightMargin=20 * mm,
                            topMargin=20 * mm, bottomMargin=20 * mm,
                            title='5 segnali che il margine della tua PMI sta scendendo',
                            author='Maurizio Gustinicchi', subject='Guida pratica per titolari di PMI')
    st = []

    # --- Copertina
    st.append(Spacer(1, 52 * mm))
    st.append(Paragraph('GUIDA PRATICA PER TITOLARI DI PMI', ParagraphStyle(
        'k', parent=S['kicker'], textColor=colors.HexColor('#ff8a8a'), fontSize=10)))
    st.append(Spacer(1, 4))
    st.append(Paragraph('5 segnali che il margine<br/>della tua PMI sta scendendo', S['h1']))
    st.append(Spacer(1, 10))
    st.append(Paragraph('…e come accorgertene prima che lo dica il bilancio', S['sub']))
    st.append(Spacer(1, 30 * mm))
    if os.path.exists(FOTO):
        foto = Image(FOTO, width=42 * mm, height=31.5 * mm)
        autore = Paragraph('<b>Maurizio Gustinicchi</b><br/>Controller (AssoController) · Innovation Manager '
                           'certificato DNV (UNI 11814)<br/>Consulente indipendente dal 1998',
                           ParagraphStyle('a', parent=S['sub'], fontSize=10.5, leading=15))
        t = Table([[foto, autore]], colWidths=[48 * mm, 122 * mm])
        t.setStyle(TableStyle([('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (-1, -1), 0)]))
        st.append(t)
    st.append(PageBreak())

    # --- Introduzione
    st.append(Paragraph('PERCHÉ QUESTA GUIDA', S['kicker']))
    st.append(Paragraph('Il bilancio arriva sempre troppo tardi', S['h2']))
    st.append(Paragraph(
        "Nella maggior parte delle piccole e medie imprese i numeri si guardano a fine anno, quando il "
        "commercialista consegna il bilancio. A quel punto il margine perso è già perso: si può solo "
        "prendere atto.", S['p']))
    st.append(Paragraph(
        "Eppure i problemi di margine lasciano tracce molto prima: nella cassa, negli incassi, nelle "
        "commesse, nel magazzino. In questa guida trovi i <b>5 segnali</b> che incontro più spesso nel mio "
        "lavoro di controller, con un modo semplice per misurarli e cosa fare subito.", S['p']))
    st.append(Spacer(1, 6))
    st.append(riquadro(Paragraph(
        "<b>Non serve un software costoso per iniziare.</b> Per ogni segnale trovi una misura che puoi "
        "calcolare anche con i dati che hai già. Il passo successivo è averla aggiornata in automatico, "
        "senza aspettare la fine dell'anno.", S['box']), bordo=RED))
    st.append(Spacer(1, 10))
    st.append(Paragraph(
        "C'è anche un motivo di legge: l'articolo 2086 del Codice Civile chiede all'imprenditore di dotarsi "
        "di un assetto organizzativo, amministrativo e contabile adeguato, anche per rilevare per tempo "
        "i segnali di crisi. Guardare questi indicatori con regolarità va esattamente in quella direzione.",
        S['p']))

    # --- I 5 segnali
    for i, sgn in enumerate(SEGNALI, 1):
        blocco = [
            Spacer(1, 10),
            Paragraph(f'SEGNALE {i} DI 5', S['kicker']),
            Paragraph(sgn['titolo'], S['h2']),
            Paragraph('Cosa vedi', S['h3']), Paragraph(sgn['cosa'], S['p']),
            Paragraph('Perché è pericoloso', S['h3']), Paragraph(sgn['perche'], S['p']),
            Paragraph('Come misurarlo', S['h3']), riquadro(Paragraph(sgn['misura'], S['formula'])),
            Paragraph('Cosa fare subito', S['h3']), Paragraph(sgn['fare'], S['p']),
        ]
        if i in (1, 3, 5):
            st.append(PageBreak())
        st.append(KeepTogether(blocco))

    # --- Checklist
    st.append(PageBreak())
    st.append(Paragraph('AUTOVALUTAZIONE', S['kicker']))
    st.append(Paragraph('Check-up in 2 minuti', S['h2']))
    st.append(Paragraph('Segna le affermazioni vere per la tua azienda. Ogni casella vuota è un punto '
                        'da cui partire.', S['p']))
    righe = [['', Paragraph(t, S['box'])] for t in CHECKLIST]
    t = Table(righe, colWidths=[12 * mm, 158 * mm])
    t.setStyle(TableStyle([
        ('BOX', (0, 0), (0, -1), 0, colors.white),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LINEBELOW', (0, 0), (-1, -1), 0.5, colors.HexColor('#dfe5ee')),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
    ]))
    for r in range(len(righe)):
        t.setStyle(TableStyle([('BOX', (0, r), (0, r), 1.2, NAVY)]))
    st.append(t)
    st.append(Spacer(1, 10))
    st.append(riquadro(Paragraph(
        '<b>0-3 caselle vuote:</b> hai una buona base, lavora sui punti mancanti.<br/>'
        '<b>4-6 caselle vuote:</b> stai decidendo con informazioni parziali: è il momento di un controllo '
        'di gestione strutturato.<br/>'
        '<b>7-8 caselle vuote:</b> il rischio di scoprire i problemi tardi è alto. Parliamone.', S['box'])))

    # --- Come posso aiutarti
    st.append(Spacer(1, 16))
    st.append(Paragraph('IL PASSO SUCCESSIVO', S['kicker']))
    st.append(Paragraph('Come lavoro con le PMI', S['h2']))
    st.append(Paragraph(
        "<b>Un CFO per la tua azienda, senza assumerlo.</b> Unisco trent'anni di controllo di gestione "
        "industriale con modelli costruiti sui tuoi dati: previsione di cassa, margini per prodotto e "
        "commessa, analisi degli scostamenti, allerta sulle anomalie.", S['p']))
    st.append(Paragraph(
        "<b>Programmi su misura, senza costi di licenza.</b> Scrivo applicativi web sui processi reali "
        "dell'azienda: produzione, magazzino, amministrazione, qualità, acquisti. I numeri arrivano "
        "da un unico sistema, aggiornati, consultabili da PC, tablet e smartphone.", S['p']))
    st.append(Spacer(1, 8))
    st.append(riquadro(Paragraph(
        '<b>Prenota una prima consulenza conoscitiva</b><br/>'
        'Scrivimi a <b>info@mauriziogustinicchiconsulting.it</b> oppure dal sito '
        '<b>www.mauriziogustinicchiconsulting.it/contatti</b>', S['center']), sfondo=colors.HexColor('#e8eef7')))
    st.append(Spacer(1, 14))
    st.append(Paragraph('Le misure proposte sono indicazioni generali: la loro applicazione va adattata alla '
                        'realtà di ciascuna azienda. © Maurizio Gustinicchi Consulting.', S['small']))

    doc.build(st, onFirstPage=copertina, onLaterPages=pagina)
    return OUT


if __name__ == '__main__':
    print(costruisci())
