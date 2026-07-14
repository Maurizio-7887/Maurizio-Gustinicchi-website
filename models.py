# -*- coding: utf-8 -*-
from datetime import datetime, date
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class Articolo(db.Model):
    __tablename__ = 'articoli'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    titolo = db.Column(db.String(300), nullable=False)
    meta_description = db.Column(db.Text, default='')
    excerpt = db.Column(db.Text, default='')          # riassunto per la card in /blog
    cover = db.Column(db.String(400), default='')     # path immagine copertina
    body = db.Column(db.Text, nullable=False)         # HTML del contenuto articolo
    styles = db.Column(db.Text, default='')           # eventuale <style> specifico
    data_pubblicazione = db.Column(db.Date, default=date.today)
    pubblicato = db.Column(db.Boolean, default=True)
    creato_il = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def data_it(self):
        mesi = ['Gennaio', 'Febbraio', 'Marzo', 'Aprile', 'Maggio', 'Giugno',
                'Luglio', 'Agosto', 'Settembre', 'Ottobre', 'Novembre', 'Dicembre']
        d = self.data_pubblicazione
        return f'{d.day} {mesi[d.month - 1]} {d.year}'


class Lead(db.Model):
    __tablename__ = 'leads'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    azienda = db.Column(db.String(200), default='')
    telefono = db.Column(db.String(50), default='')
    messaggio = db.Column(db.Text, nullable=False)
    fonte = db.Column(db.String(100), default='sito_web')
    pagina_origine = db.Column(db.String(400), default='')
    sincronizzato_crm = db.Column(db.Boolean, default=False)
    risposta_crm = db.Column(db.Text, default='')
    notificato_desktop = db.Column(db.Boolean, default=False)
    creato_il = db.Column(db.DateTime, default=datetime.utcnow)


class Prodotto(db.Model):
    __tablename__ = 'prodotti'
    id = db.Column(db.Integer, primary_key=True)
    slug = db.Column(db.String(200), unique=True, nullable=False, index=True)
    nome = db.Column(db.String(300), nullable=False)
    descrizione = db.Column(db.Text, default='')
    tipo = db.Column(db.String(30), default='libro')     # libro | software
    prezzo_cent = db.Column(db.Integer, nullable=False)  # prezzo in centesimi (es. 2490 = 24,90€)
    spedizione_cent = db.Column(db.Integer, default=500) # costo spedizione in centesimi
    immagine = db.Column(db.String(400), default='')
    attivo = db.Column(db.Boolean, default=True)
    creato_il = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def prezzo_eur(self):
        return f'{self.prezzo_cent / 100:.2f}'.replace('.', ',')

    @property
    def spedizione_eur(self):
        return f'{self.spedizione_cent / 100:.2f}'.replace('.', ',')


class Ordine(db.Model):
    __tablename__ = 'ordini'
    id = db.Column(db.Integer, primary_key=True)
    prodotto_id = db.Column(db.Integer, db.ForeignKey('prodotti.id'), nullable=False)
    prodotto = db.relationship('Prodotto', backref='ordini')
    quantita = db.Column(db.Integer, default=1)
    totale_cent = db.Column(db.Integer, nullable=False)
    # Dati cliente e spedizione
    nome = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(200), nullable=False)
    telefono = db.Column(db.String(50), default='')
    indirizzo = db.Column(db.String(300), default='')
    cap = db.Column(db.String(10), default='')
    citta = db.Column(db.String(120), default='')
    provincia = db.Column(db.String(4), default='')
    note = db.Column(db.Text, default='')
    # Stati: in_attesa_pagamento -> pagato -> spedito  (bonifico: da_confermare -> pagato -> spedito)
    stato = db.Column(db.String(30), default='in_attesa_pagamento')
    metodo_pagamento = db.Column(db.String(30), default='stripe')  # stripe | bonifico
    stripe_session_id = db.Column(db.String(300), default='')
    sincronizzato_crm = db.Column(db.Boolean, default=False)
    creato_il = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def totale_eur(self):
        return f'{self.totale_cent / 100:.2f}'.replace('.', ',')
