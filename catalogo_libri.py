"""Dati editoriali e listino proposto. Nessuna scrittura automatica al database."""
CATALOGO_LIBRI = {
    'marketing-di-successo': {
        'nome': 'LA RAGIONERIA DEL MARGINE PER ADDETTI AL MARKETING — Nuova Edizione',
        'descrizione': "Il nuovo Marketer-Controller AI-Driven: costificazione, allocazione dei costi e analisi del budget marketing. Un manuale professionale per collegare le decisioni di marketing alla marginalità.",
        'immagine': '/static/img/libro-ragioneria-margine-marketing.jpg',
        'prezzo_cent': 5900,
    },
    'professionista-segreteria-ceo': {
        'nome': "IL PROFESSIONISTA QUALIFICATO DI SEGRETERIA E L'ASSISTENTE DEL CEO: Competenze, Strategie e Successo",
        'descrizione': "Un manuale professionale per l'Executive Assistant: organizzazione, Time Management, comunicazione e Accounting a supporto della direzione.",
        'immagine': '/static/img/libro-executive-assistant.jpg',
        'prezzo_cent': 4900,
    },
    'distruzione-creatrice-4-0': {
        'nome': "LA DISTRUZIONE CREATRICE 4.0: COMANDARE L'AI PER MARGINALIZZARE",
        'descrizione': "Distruzione Creatrice, Intelligenza Artificiale e Python: un percorso operativo sul controllo degli algoritmi e sulle decisioni per CFO, Controller e Operations Manager.",
        'immagine': '/static/img/libro-la-distruzione-creatrice.jpg',
        'prezzo_cent': 7900,
    },
}


def aggiorna_libri(session, modello, *, applica=False):
    """Aggiorna solo i tre libri riconosciuti, in una transazione esplicita.

    Non cambia ID, slug, spedizione, disponibilità, software o ordini preesistenti.
    In anteprima non modifica nemmeno gli oggetti in memoria.
    """
    modifiche = []
    for slug, valori in CATALOGO_LIBRI.items():
        prodotto = session.query(modello).filter_by(slug=slug, tipo='libro').one_or_none()
        if prodotto is None:
            modifiche.append({'slug': slug, 'mancante': True, 'campi': {}})
            continue
        campi = {campo: {'prima': getattr(prodotto, campo), 'dopo': valore}
                 for campo, valore in valori.items() if getattr(prodotto, campo) != valore}
        modifiche.append({'slug': slug, 'mancante': False, 'campi': campi})
        if applica:
            for campo, cambiamento in campi.items():
                setattr(prodotto, campo, cambiamento['dopo'])
    if applica:
        try:
            session.commit()
        except Exception:
            session.rollback()
            raise
    return modifiche
