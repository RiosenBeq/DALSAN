"""Faz 2a güvenlik tabanı (docs/17-V2-TASARIM.md §10.5).

Bu dosyadaki her test, Faz 0 denetiminde (docs/AUDIT.md) KODDAN doğrulanmış
bir açığın kapalı kaldığını korur. Test adı açığı, docstring saldırıyı anlatır.
"""

from __future__ import annotations

import dataclasses

import pytest
from fastapi.testclient import TestClient

from app.uygulama import uygulama_olustur
from app.web.giris import cerez_gecerli, cerez_uret, denemeleri_sifirla

SIFRE = "dalsan2026"
TURKCE_SIFRE = "şİğüçö2026"


@pytest.fixture(autouse=True)
def _kilitleri_temizle():
    denemeleri_sifirla()
    yield
    denemeleri_sifirla()


def _istemci(test_ayarlari, sifre: str, env: str | None = None) -> TestClient:
    ayarlar = dataclasses.replace(test_ayarlari, yonetici_sifresi=sifre)
    if env is not None:
        ayarlar.env_yolu.write_text(env, encoding="utf-8")
    return TestClient(uygulama_olustur(ayarlar, analiz=False))


# ------------------------------------------------ R7: kilit X-Forwarded-For ile atlanmaz


def test_sahte_x_forwarded_for_kilidi_atlatamaz(test_ayarlari):
    """Saldırgan her denemede başka bir X-Forwarded-For uydurur. Eski kod o
    başlığın İLK değerini adres sayıyordu: her deneme 'yeni bir adres' olur,
    kilit hiç tetiklenmez ve şifre sınırsız denenirdi."""
    with _istemci(test_ayarlari, SIFRE) as istemci:
        for i in range(5):
            istemci.post(
                "/giris",
                data={"sifre": "yanlis", "sonra": "/"},
                headers={"x-forwarded-for": f"10.9.8.{i}"},
            )
        yanit = istemci.post(
            "/giris",
            data={"sifre": "yanlis", "sonra": "/"},
            headers={"x-forwarded-for": "10.9.8.250"},
            follow_redirects=False,
        )
        assert "kilit=" in yanit.headers["location"]


def test_kilitliyken_sahte_basliklarla_dogru_sifre_de_gecmez(test_ayarlari):
    with _istemci(test_ayarlari, SIFRE) as istemci:
        for _ in range(5):
            istemci.post("/giris", data={"sifre": "yanlis", "sonra": "/"})
        yanit = istemci.post(
            "/giris",
            data={"sifre": SIFRE, "sonra": "/"},
            headers={"x-forwarded-for": "192.0.2.77"},
            follow_redirects=False,
        )
        assert "kilit=" in yanit.headers["location"]


# ------------------------------------------- R15: Türkçe karakterli şifre 500 vermez


def test_turkce_karakterli_sifreyle_giris_calisir(test_ayarlari):
    """hmac.compare_digest iki METNİ ASCII dışında karşılaştıramaz; 'ş' içeren
    şifre kurulduğunda doğru şifreyle giriş bile 500 veriyordu."""
    with _istemci(test_ayarlari, TURKCE_SIFRE) as istemci:
        yanit = istemci.post(
            "/giris", data={"sifre": TURKCE_SIFRE, "sonra": "/"}, follow_redirects=False
        )
        assert yanit.status_code == 303
        assert yanit.headers["location"] == "/"
        assert istemci.get("/kameralar", follow_redirects=False).status_code == 200


def test_giris_kutusuna_turkce_harf_yazmak_500_vermez(test_ayarlari):
    with _istemci(test_ayarlari, SIFRE) as istemci:
        yanit = istemci.post(
            "/giris", data={"sifre": "şifreğ", "sonra": "/"}, follow_redirects=False
        )
        assert yanit.status_code == 303
        assert "hata=1" in yanit.headers["location"]


def test_ascii_disi_cerez_imzasi_cokmez():
    assert cerez_gecerli("9999999999.şğ", SIFRE) is False
    assert cerez_gecerli(cerez_uret(TURKCE_SIFRE), TURKCE_SIFRE) is True


# ------------------------------------------------ R9: şifre sayfaya basılmaz


def _girisli(istemci: TestClient, sifre: str) -> None:
    istemci.post("/giris", data={"sifre": sifre, "sonra": "/"})


TAM_FORM = {
    "ANONS": "null",
    "ANONS_HTTP_ADRESI": "",
    "ANONS_BEKLEME_SN": "30",
    "TESPIT_INSAN_GUVEN_ESIGI": "0.28",
    "TESPIT_GUVEN_ESIGI": "0.35",
    "TESPIT_NMS_ESIGI": "0.45",
    "TESPIT_EN_KUCUK_KENAR_PX": "12",
    "GORUNTU_IYILESTIRME": "kapali",
    "CIKARIM_CIHAZI": "cpu",
    "OLAY_SAKLAMA_GUN": "180",
    "GORUNTU_SAKLAMA_GUN": "90",
    "KKD_HAM_VERI_SAKLAMA_GUN": "30",
    "SISTEM_OLAY_SAKLAMA_GUN": "90",
    "DISK_UYARI_GB": "5",
    "NESNE_ESLESME_ESIGI": "0.24",
}


def _env(sifre: str) -> str:
    return f"# ayar\nYONETICI_SIFRESI={sifre}\nSUNUCU_ADRESI=127.0.0.1\n"


def test_ayarlar_sayfasi_sifreyi_gostermez(test_ayarlari):
    """Şifre `type=text` kutuda DEĞERİYLE basılıyordu: sayfa kaynağında,
    tarayıcı önbelleğinde ve ekran görüntüsünde okunabiliyordu."""
    with _istemci(test_ayarlari, SIFRE, _env(SIFRE)) as istemci:
        _girisli(istemci, SIFRE)
        sayfa = istemci.get("/ayarlar").text
        assert SIFRE not in sayfa
        assert 'type="password" name="YONETICI_SIFRESI" value=""' in sayfa
        assert "Şifre kurulu." in sayfa


def test_bos_sifre_kutusu_mevcut_sifreyi_korur(test_ayarlari):
    """Kutu artık boş gelir. Başka bir ayarı kaydeden kullanıcının şifresi
    sessizce silinmemeli."""
    with _istemci(test_ayarlari, SIFRE, _env(SIFRE)) as istemci:
        _girisli(istemci, SIFRE)
        yanit = istemci.post(
            "/ayarlar/kaydet",
            data={**TAM_FORM, "YONETICI_SIFRESI": "", "DISK_UYARI_GB": "7"},
            follow_redirects=False,
        )
        assert yanit.status_code == 303
        metin = test_ayarlari.env_yolu.read_text(encoding="utf-8")
        assert f"YONETICI_SIFRESI={SIFRE}" in metin
        assert "DISK_UYARI_GB=7" in metin


def test_yeni_sifre_yazilinca_degisir(test_ayarlari):
    with _istemci(test_ayarlari, SIFRE, _env(SIFRE)) as istemci:
        _girisli(istemci, SIFRE)
        istemci.post("/ayarlar/kaydet", data={**TAM_FORM, "YONETICI_SIFRESI": "yeni-sifre-9"})
        assert "YONETICI_SIFRESI=yeni-sifre-9" in test_ayarlari.env_yolu.read_text(encoding="utf-8")


def test_sifreyi_kaldir_kutusu_sifreyi_siler(test_ayarlari):
    with _istemci(test_ayarlari, SIFRE, _env(SIFRE)) as istemci:
        _girisli(istemci, SIFRE)
        istemci.post(
            "/ayarlar/kaydet",
            data={**TAM_FORM, "YONETICI_SIFRESI": "", "YONETICI_SIFRESI_KALDIR": "1"},
        )
        metin = test_ayarlari.env_yolu.read_text(encoding="utf-8")
        assert "YONETICI_SIFRESI=\n" in metin


def test_ag_acikken_sifre_kaldirilamaz(test_ayarlari):
    """Ağa açık + şifresiz kurulum oluşamaz (docs/15): kaldırma isteği de
    açılış doğrulayıcısından geçer, dosyaya hiçbir şey yazılmaz."""
    env = f"YONETICI_SIFRESI={SIFRE}\nSUNUCU_ADRESI=0.0.0.0\n"
    with _istemci(test_ayarlari, SIFRE, env) as istemci:
        _girisli(istemci, SIFRE)
        yanit = istemci.post(
            "/ayarlar/kaydet",
            data={**TAM_FORM, "YONETICI_SIFRESI_KALDIR": "1"},
            follow_redirects=False,
        )
        assert yanit.status_code != 303
        assert test_ayarlari.env_yolu.read_text(encoding="utf-8") == env
