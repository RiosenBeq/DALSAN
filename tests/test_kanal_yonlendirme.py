"""Kanal satırlarından yönlendirme (docs/17 §7.3-1, K22).

Olay kameranın bölümündeki BÜTÜN açık kanallara gider; bölümde kanal yoksa
"Tüm fabrika" kanallarına; hiç kanal yoksa ses çalmaz ve bunu söyler.
Güncellemeden önce .env'deki anons nereden duyuluyorsa aktarımdan sonra da
oradan duyulur.
"""

from __future__ import annotations

import pytest

from app import veritabani
from app.olaylar import anons
from app.olaylar.anons import AnonsYoneticisi, bolgeleri_sec, kanal_anonscu
from app.olaylar.kanallar import env_anonsunu_aktar


def _kanal(kid: int, alan: str, tur: str = "http", acik: int = 1, **ek) -> dict:
    return {
        "id": kid,
        "name": f"K{kid}",
        "area": alan,
        "kind": tur,
        "address": ek.get("address", f"http://10.0.0.{kid}/anons"),
        "device": ek.get("device", ""),
        "enabled": acik,
    }


def test_bolumun_butun_kanallari_secilir():
    kanallar = [
        _kanal(1, "Sevkiyat"),
        _kanal(2, "Sevkiyat", "ses_karti", device="alsa_output.pci"),
        _kanal(3, "Sevkiyat", acik=0),
        _kanal(4, ""),
    ]
    assert [k["id"] for k in bolgeleri_sec(kanallar, "Sevkiyat")] == [1, 2]
    # Bölümünde kanal olmayan olay "Tüm fabrika"ya düşer
    assert [k["id"] for k in bolgeleri_sec(kanallar, "Döküm")] == [4]
    assert [k["id"] for k in bolgeleri_sec(kanallar, "")] == [4]
    assert bolgeleri_sec([_kanal(1, "Sevkiyat")], "Döküm") == []


def test_kanal_turune_gore_adaptor():
    ses = kanal_anonscu(_kanal(1, "", "ses_karti", device="bluez_output.AA_BB.1"))
    assert isinstance(ses, anons.SesKartiAnonscu) and ses.cihaz == "bluez_output.AA_BB.1"
    http = kanal_anonscu(_kanal(2, ""), "get")
    assert isinstance(http, anons.HttpAnonscu)
    assert (http.adres, http.bicim) == ("http://10.0.0.2/anons", "get")


@pytest.fixture
def calinanlar(monkeypatch):
    kayit: list[tuple] = []

    def _ses_cal(self, anahtar, metin, ses, kes=None):
        kayit.append(("ses_karti", self.cihaz, anahtar))

    def _http_cal(self, anahtar, metin, ses, kes=None):
        kayit.append(("http", self.adres, anahtar))

    monkeypatch.setattr(anons.SesKartiAnonscu, "cal", _ses_cal)
    monkeypatch.setattr(anons.HttpAnonscu, "cal", _http_cal)
    monkeypatch.setattr(AnonsYoneticisi, "_son_anonsu_yaz", lambda *_: None)
    return kayit


MESAJ = {"id": 1, "key": "helmet", "text": "Baret takınız", "enabled": 1, "audio_file": None}


def test_olay_bolumun_her_kanalindan_duyurulur(test_ayarlari, calinanlar):
    yonetici = AnonsYoneticisi(test_ayarlari)
    yonetici.bolgeleri_yukle(
        [
            _kanal(1, "Sevkiyat"),
            _kanal(2, "Sevkiyat", "ses_karti", device="alsa_output.pci"),
            _kanal(3, ""),
        ]
    )
    yonetici.duyur(7, "Sevkiyat", 0.0, MESAJ)
    assert yonetici.bosalt()
    # İki kanal ayrı çıkışlardır: kendi işçilerinde, sırası belirsiz çalar
    assert sorted(calinanlar) == [
        ("http", "http://10.0.0.1/anons", "helmet"),
        ("ses_karti", "alsa_output.pci", "helmet"),
    ]
    assert yonetici.ad == "3 sesli kanal"


def test_kanal_yoksa_ses_calmaz_ve_soyler(test_ayarlari, calinanlar):
    yonetici = AnonsYoneticisi(test_ayarlari)
    yonetici.duyur(7, "Sevkiyat", 0.0, MESAJ)
    assert calinanlar == []
    assert "sesli kanal tanımlı değil" in yonetici.son_sonuc
    assert yonetici.ad == "sesli kanal yok"


def test_anonsu_dene_tum_fabrika_kanallarindan_calar(test_ayarlari, calinanlar):
    yonetici = AnonsYoneticisi(test_ayarlari)
    yonetici.bolgeleri_yukle([_kanal(1, "Sevkiyat"), _kanal(2, "")])
    yonetici.hemen_cal(MESAJ)
    assert yonetici.bosalt()
    assert calinanlar == [("http", "http://10.0.0.2/anons", "helmet")]


def test_anonsu_dene_tum_fabrika_yoksa_bunu_soyler(test_ayarlari, calinanlar):
    """Kanal VAR ama hepsi bir bölüme bağlı: "sesli kanal yok" demek yanlış olurdu."""
    yonetici = AnonsYoneticisi(test_ayarlari)
    yonetici.bolgeleri_yukle([_kanal(1, "Sevkiyat")])
    yonetici.hemen_cal(MESAJ)
    assert calinanlar == []
    assert "“Tüm fabrika” kanalı yok" in yonetici.son_sonuc
    assert "sesli kanal tanımlı değil" not in yonetici.son_sonuc


@pytest.mark.parametrize(
    ("env", "beklenen"),
    [
        (
            "ANONS=ses_karti\nANONS_SES_CIHAZI=bluez_output.AA_BB.1\n",
            ("ses_karti", "bluez_output.AA_BB.1", "helmet"),
        ),
        (
            "ANONS=http\nANONS_HTTP_ADRESI=http://10.0.0.9/anons\n",
            ("http", "http://10.0.0.9/anons", "helmet"),
        ),
    ],
)
def test_aktarimdan_sonra_ayni_cikis_calar(test_ayarlari, calinanlar, env, beklenen):
    """Güncellemeden önce anons .env'deki çıkıştan çalıyordu; aktarımdan sonra
    "Tüm fabrika" satırı olarak aynı yerden çalar (docs/17 §13 4a)."""
    test_ayarlari.env_yolu.write_text(env, encoding="utf-8")
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        env_anonsunu_aktar(baglanti, test_ayarlari.env_yolu)
        satirlar = baglanti.execute("SELECT * FROM speaker_zones ORDER BY id").fetchall()
    finally:
        baglanti.close()
    yonetici = AnonsYoneticisi(test_ayarlari)
    yonetici.bolgeleri_yukle(satirlar)
    yonetici.duyur(7, "Sevkiyat", 0.0, MESAJ)
    assert yonetici.bosalt()
    assert calinanlar == [beklenen]
