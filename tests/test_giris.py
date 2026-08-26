"""Giriş / oturum testleri: şifresiz erişim yok (docs/01 §3.6)."""

from __future__ import annotations

from app.web.giris import cerez_gecerli, cerez_uret


def test_oturumsuz_sayfa_girise_yonlenir(ham_istemci):
    for yol in ("/", "/kameralar", "/kurallar", "/olaylar", "/kkd"):
        yanit = ham_istemci.get(yol, headers={"accept": "text/html"}, follow_redirects=False)
        assert yanit.status_code == 303, yol
        assert yanit.headers["location"].startswith("/giris")


def test_oturumsuz_api_401_doner(ham_istemci):
    yanit = ham_istemci.get("/kameralar/1/onizleme.jpg", follow_redirects=False)
    assert yanit.status_code == 401


def test_yanlis_sifre_giris_yapamaz(ham_istemci):
    yanit = ham_istemci.post(
        "/giris", data={"sifre": "yanlis-sifre", "sonra": "/"}, follow_redirects=False
    )
    assert yanit.status_code == 303
    assert "hata=1" in yanit.headers["location"]
    # hâlâ oturumsuz
    yanit = ham_istemci.get("/", headers={"accept": "text/html"}, follow_redirects=False)
    assert yanit.status_code == 303


def test_dogru_sifre_giris_yapar(istemci):
    yanit = istemci.get("/")
    assert yanit.status_code == 200
    assert "DALSAN" in yanit.text


def test_cerez_imzasi_taklit_edilemez():
    sifre = "gizli"
    cerez = cerez_uret(sifre)
    assert cerez_gecerli(cerez, sifre)
    assert not cerez_gecerli(cerez, "baska-sifre")  # farklı şifreyle imza tutmaz
    assert not cerez_gecerli(cerez + "x", sifre)
    assert not cerez_gecerli("999999999999.sahte-imza", sifre)
    assert not cerez_gecerli(None, sifre)


def test_suresi_dolan_cerez_gecersiz():
    sifre = "gizli"
    eski = cerez_uret(sifre, simdi=0.0)  # 1970'te açılan oturum
    assert not cerez_gecerli(eski, sifre)


def test_acik_yonlendirme_engellenir(ham_istemci):
    from conftest import TEST_SIFRESI

    # Tarayıcının dış adrese götürdüğü TÜM biçimler site köküne düşmeli
    for kotu in ("https://kotu-site.example", "//kotu-site.example", "/\\kotu-site.example"):
        yanit = ham_istemci.post(
            "/giris",
            data={"sifre": TEST_SIFRESI, "sonra": kotu},
            follow_redirects=False,
        )
        assert yanit.headers["location"] == "/", kotu
    # Site içi normal yol korunmalı
    yanit = ham_istemci.post(
        "/giris", data={"sifre": TEST_SIFRESI, "sonra": "/kameralar"}, follow_redirects=False
    )
    assert yanit.headers["location"] == "/kameralar"
