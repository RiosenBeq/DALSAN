"""TEK giriş noktası. Kontrol Paneli sistemi şu komutla başlatır (değiştirilemez):

    uvicorn app.main:app --host 127.0.0.1 --port 8080   (çalışma dizini: backend/)

Bu dosya .env'den ayarları yükler, log sistemini kurar ve FastAPI uygulamasını
`app` adıyla dışa verir. Uygulamanın kendisi app/uygulama.py'de kurulur;
testler o fabrikayı bu dosyayı hiç import etmeden kullanır.
"""

from __future__ import annotations

import sys

from fastapi import FastAPI

from app import loglama
from app.ayarlar import ayarlari_yukle
from app.hatalar import AyarHatasi
from app.uygulama import uygulama_olustur


def _ana_uygulama() -> FastAPI:
    try:
        ayarlar = ayarlari_yukle()
    except AyarHatasi as hata:
        # Traceback yerine, Kontrol Paneli günlüğünde olduğu gibi okunacak
        # anlaşılır bir Türkçe mesajla dur. Sistem yarım ayarla çalışmaz.
        print(f"\n[AYAR HATASI] {hata.kullanici_mesaji}\n", file=sys.stderr)
        raise SystemExit(1) from hata
    loglama.kur(ayarlar)
    return uygulama_olustur(ayarlar)


app = _ana_uygulama()
