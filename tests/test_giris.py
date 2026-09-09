"""Giriş / oturum (web/giris.py).

Sınanan iki söz:
  · ŞİFRE BOŞKEN bugünkü yerel kullanım aynen sürer — hiçbir yerde şifre
    sorulmaz. Kullanıcı kendi bilgisayarında sistemi denerken engellenmemeli.
  · ŞİFRE DOLUYKEN hiçbir sayfa açılmaz. Kural değiştirebilen, kamera
    silebilen ve hoparlörden anons yaptırabilen bir sistem şirket ağında
    bile şifresiz durmamalı.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.uygulama import uygulama_olustur
from app.web.giris import cerez_gecerli, cerez_uret

SIFRE = "dalsan2026"

# Şifre koyunca korunması BEKLENEN sayfalar — her biri sistemi değiştirebilir
# ya da fabrika görüntüsü/olay geçmişi gösterir.
KORUMALI_YOLLAR = (
    "/",
    "/kameralar",
    "/kurallar",
    "/olaylar",
    "/kkd",
    "/anons",
    "/nesneler",
    "/ayarlar",
    "/komuta",
    "/komuta/duvar",
    "/komuta/inceleme",
    "/komuta/anons",
)


@pytest.fixture
def sifreli_ayarlar(test_ayarlari):
    return dataclasses.replace(test_ayarlari, yonetici_sifresi=SIFRE)


@pytest.fixture
def sifreli_istemci(sifreli_ayarlar):
    """Şifreli sistem + TARAYICI gibi davranan istemci.

    `Accept: text/html` başlığı bilerek verilir: gerçek tarayıcı bunu gönderir
    ve yetki hatası giriş sayfasına YÖNLENDİRİLİR. Başlıksız bir istemci
    (fetch çağrısı gibi) 401 JSON alır — o da ayrıca sınanır.
    """
    uygulama = uygulama_olustur(sifreli_ayarlar, analiz=False)
    with TestClient(uygulama, headers={"accept": "text/html"}) as istemci:
        yield istemci


# ------------------------------------------------------------ şifre YOKKEN


def test_sifresizken_hicbir_sayfa_giris_istemez(istemci):
    for yol in KORUMALI_YOLLAR:
        assert istemci.get(yol).status_code == 200, yol


def test_sifresizken_cikis_dugmesi_gorunmez(istemci):
    """Basıldığında hiçbir işe yaramayan düğme, olmayan düğmeden kötüdür."""
    assert "/cikis" not in istemci.get("/komuta").text
    assert "/cikis" not in istemci.get("/kameralar").text


def test_sifresizken_kurulum_listesi_uyariyor(istemci):
    """Sessiz bir güvenlik açığı, olmayan güvenlikten kötüdür."""
    sayfa = istemci.get("/komuta").text
    assert "Şifre yok" in sayfa
    assert "fabrika sunucusuna" in sayfa.lower()


# ------------------------------------------------------------ şifre VARKEN


def test_sifreliyken_her_sayfa_girise_yonlenir(sifreli_istemci):
    for yol in KORUMALI_YOLLAR:
        yanit = sifreli_istemci.get(yol, follow_redirects=False)
        assert yanit.status_code == 303, yol
        assert yanit.headers["location"].startswith("/giris"), yol


def test_dogru_sifre_iceri_alir(sifreli_istemci):
    yanit = sifreli_istemci.post(
        "/giris", data={"sifre": SIFRE, "sonra": "/kameralar"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"] == "/kameralar"
    assert sifreli_istemci.get("/kameralar").status_code == 200


def test_yanlis_sifre_iceri_almaz(sifreli_istemci):
    yanit = sifreli_istemci.post(
        "/giris", data={"sifre": "yanlis", "sonra": "/"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert "hata=1" in yanit.headers["location"]
    assert sifreli_istemci.get("/", follow_redirects=False).status_code == 303


def test_cikis_oturumu_kapatir(sifreli_istemci):
    sifreli_istemci.post("/giris", data={"sifre": SIFRE, "sonra": "/"})
    assert sifreli_istemci.get("/kameralar").status_code == 200
    sifreli_istemci.post("/cikis")
    assert sifreli_istemci.get("/kameralar", follow_redirects=False).status_code == 303


def test_giris_sayfasi_sifresiz_acilir(sifreli_istemci):
    """Giriş sayfasının kendisi korunamaz: yoksa giriş yapılamaz."""
    assert sifreli_istemci.get("/giris").status_code == 200


def test_saglik_ucu_korumasiz(sifreli_istemci):
    """Docker'ın sağlık yoklaması (docker-compose.yml) giriş yapamaz."""
    assert sifreli_istemci.get("/saglik").status_code == 200


def test_favicon_korumasiz(sifreli_istemci):
    assert sifreli_istemci.get("/favicon.ico").status_code == 200


def test_js_istegi_yonlendirilmez_401_alir(sifreli_istemci):
    """fetch çağrıları yönlendirmeyle bozulmamalı: sessizce HTML almaya
    başlarlarsa arayüz teşhis edilemez biçimde çalışmaz."""
    yanit = sifreli_istemci.get(
        "/kameralar/1/durum.json",
        headers={"accept": "application/json", "sec-fetch-mode": "cors"},
    )
    assert yanit.status_code == 401
    assert "hata" in yanit.json()


def test_sayfa_gezinmesi_accept_basligi_olmadan_da_yonlenir(sifreli_istemci):
    """Bazı tarayıcı/vekil birleşimleri gezinmede `*/*` gönderir; kullanıcı
    giriş formu yerine ham JSON görmemeli."""
    yanit = sifreli_istemci.get(
        "/kameralar",
        headers={"accept": "*/*", "sec-fetch-mode": "navigate"},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    assert yanit.headers["location"].startswith("/giris")


def test_cikis_dugmesi_gorunur(sifreli_istemci):
    sifreli_istemci.post("/giris", data={"sifre": SIFRE, "sonra": "/"})
    assert "/cikis" in sifreli_istemci.get("/komuta").text


# ------------------------------------------------------- çerez ve açık yönlendirme


def test_cerez_sifre_tasimaz():
    """Çerez çalınsa bile şifre ele geçmemeli."""
    assert SIFRE not in cerez_uret(SIFRE)


def test_sifre_degisince_eski_cerez_duser():
    cerez = cerez_uret(SIFRE)
    assert cerez_gecerli(cerez, SIFRE)
    assert not cerez_gecerli(cerez, "baska-sifre")


def test_suresi_dolan_cerez_gecersiz():
    cerez = cerez_uret(SIFRE, simdi=0)
    assert not cerez_gecerli(cerez, SIFRE, simdi=10**12)


def test_bozuk_cerez_cokmez():
    for bozuk in (None, "", "abc", "abc.def", ".", "999999999999"):
        assert not cerez_gecerli(bozuk, SIFRE)


@pytest.mark.parametrize("kotu", ["//evil.com", "/\\evil.com", "https://evil.com"])
def test_acik_yonlendirme_engellenir(sifreli_istemci, kotu):
    """Giriş sayfası bir kimlik avı sıçrama tahtasına dönüşmemeli."""
    yanit = sifreli_istemci.post(
        "/giris", data={"sifre": SIFRE, "sonra": kotu}, follow_redirects=False
    )
    assert yanit.headers["location"] == "/"


def test_kisa_sifre_acilista_reddedilir(tmp_path):
    """Üç harflik bir şifre, şifre yokmuş gibi davranır — sessizce kabul edilmemeli."""
    from app.ayarlar import AyarHatasi, ayarlari_yukle

    (tmp_path / ".env").write_text("YONETICI_SIFRESI=abc\n", encoding="utf-8")
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "6 karakter" in hata.value.kullanici_mesaji
