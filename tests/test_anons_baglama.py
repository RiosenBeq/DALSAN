"""Anons sistemine bağlanma: üç HTTP biçimi, yer tutucular ve kılavuz.

Sınanan söz: fabrikadaki IP hoparlör hangi biçimi bekliyorsa sistem onu
gönderebilmeli — ve DENEME düğmesi, gerçek anonsla AYNI yoldan gitmeli.
İkisi ayrılırsa deneme "başarılı" derken saha sessiz kalır.
"""

from __future__ import annotations

import urllib.request
from pathlib import Path

import pytest

from app.olaylar import anons

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture
def yakalanan(monkeypatch):
    """urlopen'i yakalar; ağa çıkılmaz, gönderilen istek incelenir."""
    kayit = {}

    class SahteYanit:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

    def sahte_urlopen(istek, timeout=None):
        kayit["adres"] = istek.full_url
        kayit["yontem"] = istek.get_method()
        kayit["govde"] = istek.data
        kayit["tur"] = istek.headers.get("Content-type")
        return SahteYanit()

    monkeypatch.setattr(urllib.request, "urlopen", sahte_urlopen)
    return kayit


# ------------------------------------------------------------- üç biçim


def test_json_bicimi_govdede_json_gonderir(yakalanan):
    anons.http_gonder("http://10.0.0.9/anons", "helmet", "Baretinizi takınız.", "json")
    assert yakalanan["yontem"] == "POST"
    assert yakalanan["tur"] == "application/json"
    assert b'"key": "helmet"' in yakalanan["govde"]


def test_varsayilan_bicim_eskisiyle_ayni(yakalanan):
    """Biçim verilmezse davranış DEĞİŞMEMELİ: kurulu sistemler bozulmasın."""
    anons.http_gonder("http://10.0.0.9/anons", "vest", "Yeleğinizi giyiniz.")
    assert yakalanan["tur"] == "application/json"
    assert yakalanan["yontem"] == "POST"


def test_form_bicimi_form_alani_gonderir(yakalanan):
    anons.http_gonder("http://10.0.0.9/anons", "helmet", "Baret", "form")
    assert yakalanan["tur"] == "application/x-www-form-urlencoded"
    assert b"key=helmet" in yakalanan["govde"]


def test_get_bicimi_govdesiz_gider(yakalanan):
    anons.http_gonder("http://10.0.0.9/play?file={anahtar}", "helmet", "Baret", "get")
    assert yakalanan["yontem"] == "GET"
    assert yakalanan["govde"] is None
    assert yakalanan["adres"] == "http://10.0.0.9/play?file=helmet"


# --------------------------------------------------------- yer tutucular


def test_yer_tutucular_doldurulur():
    sonuc = anons.adresi_doldur(
        "http://s/play?f={anahtar}&m={metin}", "helmet", "Baretinizi takınız."
    )
    assert "f=helmet" in sonuc
    assert "Baret" in sonuc
    assert " " not in sonuc  # metin URL kaçışlı olmalı


def test_yabanci_susler_bozulmaz():
    """Anons sisteminin KENDİ süslü parantezleri anonsu susturmamalı.

    str.format kullanılsaydı bu adres KeyError fırlatır ve hiçbir anons
    çalınmazdı — sahada teşhisi en zor arıza budur.
    """
    sonuc = anons.adresi_doldur("http://s/play?q={id}&f={anahtar}", "vest", "Yelek")
    assert sonuc == "http://s/play?q={id}&f=vest"


def test_yer_tutucusuz_adres_degismez():
    adres = "http://10.0.0.9:8080/anons"
    assert anons.adresi_doldur(adres, "helmet", "Baret") == adres


# ------------------------------------------------------- bölge + ayarlar


def test_hoparlor_bolgesi_bicimi_korur(test_ayarlari, yakalanan):
    """Bölgeye giden anons da .env'deki biçimi kullanmalı."""
    ayarlar = type(test_ayarlari)(
        **{
            **test_ayarlari.__dict__,
            "anons": "http",
            "anons_http_adresi": "http://varsayilan/{anahtar}",
            "anons_http_bicimi": "get",
        }
    )
    yonetici = anons.AnonsYoneticisi(ayarlar)
    hedef = yonetici._hedef_anonscu({"address": "http://sevkiyat/{anahtar}", "name": "Sevkiyat"})
    assert hedef.bicim == "get"
    assert hedef.adres == "http://sevkiyat/{anahtar}"


def test_get_bicimi_yer_tutucusuz_adresi_reddeder(tmp_path):
    """Yer tutucusuz GET adresi HER ihlalde aynı sesi çalardı; açılışta durdurulur."""
    from app.ayarlar import AyarHatasi, ayarlari_yukle

    (tmp_path / ".env").write_text(
        "ANONS=http\nANONS_HTTP_BICIMI=get\nANONS_HTTP_ADRESI=http://10.0.0.9/play\n",
        encoding="utf-8",
    )
    with pytest.raises(AyarHatasi) as hata:
        ayarlari_yukle(tmp_path)
    assert "{anahtar}" in str(hata.value.kullanici_mesaji)


def test_get_bicimi_yer_tutuculu_adresi_kabul_eder(tmp_path):
    from app.ayarlar import ayarlari_yukle

    (tmp_path / ".env").write_text(
        "ANONS=http\nANONS_HTTP_BICIMI=get\nANONS_HTTP_ADRESI=http://10.0.0.9/play?f={anahtar}\n",
        encoding="utf-8",
    )
    ayarlar = ayarlari_yukle(tmp_path)
    assert ayarlar.anons_http_bicimi == "get"


def test_deneme_dugmesi_ayarlardaki_bicimi_kullanir():
    """Deneme ile gerçek anons AYRI biçimde giderse deneme yalan söyler."""
    kaynak = (KOK / "backend" / "app" / "web" / "hoparlorler.py").read_text(encoding="utf-8")
    assert "anons_http_bicimi" in kaynak


# --------------------------------------------------------------- kılavuz


def test_anons_kilavuzu_var():
    belge = KOK / "docs" / "14-ANONS-SISTEMI-BAGLAMA.md"
    assert belge.is_file()
    metin = belge.read_text(encoding="utf-8")
    for baslik in ("Ses kartı", "{anahtar}", "Hoparlör bölgeleri", "gölge mod"):
        assert baslik.lower() in metin.lower(), f"kılavuzda eksik: {baslik}"


def test_kilavuz_sayfasinda_anons_bolumu(istemci):
    sayfa = istemci.get("/komuta/kilavuz").text
    assert 'id="anons"' in sayfa
    assert "Anons sistemine bağlama" in sayfa
    assert "hat girişine" in sayfa  # ses kartı bağlantısının kritik uyarısı


def test_kilavuzda_devreye_alma_sirasi_var(istemci):
    """Gölge mod olmadan anons açmak, geri alınamayan bir güven kaybıdır."""
    sayfa = istemci.get("/komuta/kilavuz").text
    assert "gölge modda" in sayfa
    assert "güven" in sayfa


def test_ayarlar_sayfasinda_bicim_secimi(istemci):
    sayfa = istemci.get("/ayarlar").text
    assert "ANONS_HTTP_BICIMI" in sayfa
    assert "beklediği biçim" in sayfa
