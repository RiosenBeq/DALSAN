"""Oturum çerezinin kuruluma özgü sırrı (docs/17 §10.5 R16; Faz 5d).

Eskiden çerez imzasının anahtarı YALNIZ şifreden türüyordu: ele geçen tek bir
çerezle şifre, sunucuya hiç dokunmadan (kaba kuvvet kilidine takılmadan)
çevrimdışı denenebilirdi. Artık anahtar şifre + `veri/oturum.anahtar`'daki
rastgele sırdan türer. Şifre değişince oturumların düşmesi korunur.
"""

from __future__ import annotations

import dataclasses
import hashlib
import hmac
import os
import time

import pytest
from fastapi.testclient import TestClient

from app.uygulama import uygulama_olustur
from app.web import giris
from app.web.giris import SIR_DOSYASI, cerez_gecerli, cerez_uret, oturum_sirri

SIFRE = "dalsan2026"
CEREZ = "dalsan_oturum"
HTML = {"accept": "text/html"}


@pytest.fixture(autouse=True)
def _temiz():
    giris.denemeleri_sifirla()
    giris._sirlar.clear()
    yield
    giris.denemeleri_sifirla()
    giris._sirlar.clear()


@pytest.fixture
def ayarlar(test_ayarlari):
    return dataclasses.replace(test_ayarlari, yonetici_sifresi=SIFRE)


def _istemci(ayarlar) -> TestClient:
    return TestClient(uygulama_olustur(ayarlar, analiz=False), headers=HTML)


def _giris_yap(istemci) -> str:
    yanit = istemci.post("/giris", data={"sifre": SIFRE, "sonra": "/"}, follow_redirects=False)
    assert yanit.status_code == 303 and yanit.headers["location"] == "/"
    return istemci.cookies[CEREZ]


def _korunan_sayfa_acilir(istemci) -> bool:
    return istemci.get("/kameralar", follow_redirects=False).status_code == 200


def test_ilk_giriste_sir_uretilir_ve_yalniz_sahibi_okur(ayarlar):
    dosya = ayarlar.veri_dizini / SIR_DOSYASI
    with _istemci(ayarlar) as istemci:
        assert not dosya.exists()
        _giris_yap(istemci)
        assert _korunan_sayfa_acilir(istemci)
    assert len(bytes.fromhex(dosya.read_text(encoding="ascii"))) == 32
    if os.name != "nt":  # Windows izin bitlerini bu biçimde tutmaz
        assert dosya.stat().st_mode & 0o777 == 0o600


def test_ayni_sifre_baska_kurulumda_gecersiz():
    cerez = cerez_uret(SIFRE, sir=b"a" * 32)
    assert cerez_gecerli(cerez, SIFRE, sir=b"a" * 32)
    assert not cerez_gecerli(cerez, SIFRE, sir=b"b" * 32)


def test_sifre_degisince_oturum_yine_duser():
    cerez = cerez_uret(SIFRE, sir=b"a" * 32)
    assert not cerez_gecerli(cerez, "yeni-sifre", sir=b"a" * 32)


def test_yalniz_sifreden_imzali_cerez_reddedilir(ayarlar):
    """Eski biçim (anahtar = sha256(şifre)): şifreyi bilen ama sırrı bilmeyen
    biri çerez üretememeli. Güncellemeden sonra herkes bir kez yeniden girer."""
    son = str(int(time.time()) + 3600)
    anahtar = hashlib.sha256(("dalsan-oturum:" + SIFRE).encode("utf-8")).digest()
    eski = f"{son}.{hmac.new(anahtar, son.encode(), hashlib.sha256).hexdigest()}"
    with _istemci(ayarlar) as istemci:
        istemci.cookies.set(CEREZ, eski)
        assert not _korunan_sayfa_acilir(istemci)


def test_sir_yeniden_baslatmada_ayni_kalir(ayarlar):
    with _istemci(ayarlar) as istemci:
        cerez = _giris_yap(istemci)
    giris._sirlar.clear()  # süreç yeniden başladı: sır dosyadan okunur
    with _istemci(ayarlar) as istemci:
        istemci.cookies.set(CEREZ, cerez)
        assert _korunan_sayfa_acilir(istemci)


def test_bozuk_sir_dosyasi_yenilenir_oturumlar_duser(ayarlar):
    with _istemci(ayarlar) as istemci:
        cerez = _giris_yap(istemci)
    dosya = ayarlar.veri_dizini / SIR_DOSYASI
    dosya.write_text("bozuk", encoding="ascii")
    giris._sirlar.clear()
    with _istemci(ayarlar) as istemci:
        istemci.cookies.set(CEREZ, cerez)
        assert not _korunan_sayfa_acilir(istemci)
        istemci.cookies.clear()  # eski çerez atılır, yeni girişin çerezi tek kalsın
        _giris_yap(istemci)
        assert _korunan_sayfa_acilir(istemci)
    assert len(bytes.fromhex(dosya.read_text(encoding="ascii"))) == 32


def test_sir_kaydedilemezse_giris_yine_calisir(ayarlar, monkeypatch):
    """Salt okunur veri klasörü girişi kilitlememeli: sır bu çalışma boyunca
    bellekte durur, oturumlar yalnız yeniden başlatmada düşer."""

    def _yazilamaz(*_a, **_k):
        raise OSError("salt okunur")

    monkeypatch.setattr(giris.os, "open", _yazilamaz)
    assert len(oturum_sirri(ayarlar)) == 32
    assert oturum_sirri(ayarlar) == oturum_sirri(ayarlar)
    with _istemci(ayarlar) as istemci:
        _giris_yap(istemci)
        assert _korunan_sayfa_acilir(istemci)
    assert not (ayarlar.veri_dizini / SIR_DOSYASI).exists()
