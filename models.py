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
    creato_il = db.Column(db.DateTime, default=datetime.utcnow)
