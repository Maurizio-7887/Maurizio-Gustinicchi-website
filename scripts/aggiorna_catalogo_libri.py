"""Aggiornamento esplicito, senza importare app.py o avviare migrazioni/seed.

python scripts/aggiorna_catalogo_libri.py          # solo anteprima
python scripts/aggiorna_catalogo_libri.py --applica
Richiede DATABASE_URL nell'ambiente protetto. Non passarla sulla riga di comando.
"""
import argparse
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from flask import Flask
from models import db, Prodotto
from catalogo_libri import aggiorna_libri


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--applica', action='store_true')
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        parser.error('DATABASE_URL non impostata: nessun database è stato aperto.')
    if url.startswith(('postgres://', 'postgresql://')):
        url = 'postgresql+psycopg2://' + url.split('://', 1)[1]
    app = Flask(__name__)
    app.config.update(SQLALCHEMY_DATABASE_URI=url, SQLALCHEMY_TRACK_MODIFICATIONS=False)
    db.init_app(app)
    with app.app_context():
        risultati = aggiorna_libri(db.session, Prodotto, applica=args.applica)
        for risultato in risultati:
            print(risultato['slug'])
            if risultato['mancante']:
                print('  Libro assente: nessuna creazione automatica.')
            for campo, valori in risultato['campi'].items():
                print(f"  {campo}: {valori['prima']} -> {valori['dopo']}")
        print('Aggiornamento applicato.' if args.applica else 'Solo anteprima. Per salvare: --applica')


if __name__ == '__main__':
    main()
