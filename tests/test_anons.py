"""Anons altyapısı testleri (docs/08 R3).

Fabrikadaki anons sisteminin türü henüz bilinmiyor; bu testler üç yöntemin
(kapalı / ses kartı / HTTP) da doğru davrandığını, ihlalde otomatik anons
verildiğini ve paneldeki deneme anonsunun çalıştığını doğrular.
"""

from __future__ import annotations

import dataclasses
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from app import veritabani
from app.olaylar.anons import AnonsYoneticisi, HttpAnonscu, NullAnonscu


@pytest.fixture
def baglanti(test_ayarlari):
    b = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(b)
    yield b
    b.close()


def _mesaj(baglanti, anahtar: str = "helmet") -> dict:
    satir = baglanti.execute(
        "SELECT * FROM announcement_messages WHERE key = ?", (anahtar,)
    ).fetchone()
    return dict(satir)


# ---- yöntem seçimi ----


def test_varsayilan_yontem_kapali(test_ayarlari):
    yonetici = AnonsYoneticisi(test_ayarlari)
    assert yonetici.ad == "kapalı"


def test_kapali_yontem_ses_calmaz_ama_sebebini_soyler(test_ayarlari, baglanti):
    sonuc = AnonsYoneticisi(test_ayarlari).deneme(_mesaj(baglanti))
    assert not sonuc.basarili
    assert "kapalı" in sonuc.mesaj.lower()


def test_ses_karti_yontemi_ses_dosyasi_yoksa_uyarir(test_ayarlari, baglanti):
    ayarlar = dataclasses.replace(test_ayarlari, anons="ses_karti")
    yonetici = AnonsYoneticisi(ayarlar)
    assert yonetici.ad == "ses kartı"
    # Seed mesajlarında audio_file NULL — kullanıcıya ne yapacağı söylenmeli
    sonuc = yonetici.deneme(_mesaj(baglanti))
    assert not sonuc.basarili
    assert "ses dosyası" in sonuc.mesaj.lower()


# ---- HTTP yöntemi (IP hoparlör) ----


class _SahteHoparlor(BaseHTTPRequestHandler):
    alinan: list[bytes] = []

    def do_POST(self):
        uzunluk = int(self.headers.get("Content-Length", 0))
        _SahteHoparlor.alinan.append(self.rfile.read(uzunluk))
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # test çıktısını kirletmesin


@pytest.fixture
def sahte_hoparlor():
    _SahteHoparlor.alinan = []
    sunucu = HTTPServer(("127.0.0.1", 0), _SahteHoparlor)
    threading.Thread(target=sunucu.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{sunucu.server_port}/anons"
    sunucu.shutdown()


def test_http_yontemi_hoparlore_mesaji_gonderir(sahte_hoparlor, baglanti):
    sonuc = HttpAnonscu(sahte_hoparlor).cal("helmet", "Lütfen baretinizi takınız.", None)
    assert sonuc.basarili
    assert len(_SahteHoparlor.alinan) == 1
    govde = _SahteHoparlor.alinan[0].decode("utf-8")
    assert "helmet" in govde
    assert "baretinizi" in govde


def test_http_yontemi_ulasilamayan_adreste_sistemi_durdurmaz(baglanti):
    # Kapalı port: istisna fırlatmamalı, kullanıcıya anlaşılır hata dönmeli
    sonuc = HttpAnonscu("http://127.0.0.1:9/anons").cal("helmet", "deneme", None)
    assert not sonuc.basarili
    assert "ulaşılamadı" in sonuc.mesaj


# ---- ihlalde otomatik anons + cooldown ----


class _SayanAnonscu:
    ad = "sayaç"

    def __init__(self):
        self.cagrilar = []

    def cal(self, anahtar, metin, ses_dosyasi):
        from app.olaylar.anons import AnonsSonucu

        self.cagrilar.append((anahtar, metin))
        return AnonsSonucu(True, "çalındı")


def test_ihlalde_otomatik_anons_verilir_ve_cooldown_uygulanir(test_ayarlari, baglanti):
    yonetici = AnonsYoneticisi(test_ayarlari)
    sayan = _SayanAnonscu()
    yonetici._anonscu = sayan
    mesaj = _mesaj(baglanti)

    assert yonetici.duyur(kamera_id=1, zaman_s=100.0, mesaj=mesaj) is not None
    # conftest: bekleme 30 sn — aynı kamera+mesaj için tekrar çalmaz
    assert yonetici.duyur(kamera_id=1, zaman_s=110.0, mesaj=mesaj) is None
    # Farklı kamera bağımsızdır
    assert yonetici.duyur(kamera_id=2, zaman_s=110.0, mesaj=mesaj) is not None
    # Süre dolunca tekrar çalar
    assert yonetici.duyur(kamera_id=1, zaman_s=131.0, mesaj=mesaj) is not None
    assert len(sayan.cagrilar) == 3


def test_kapali_mesaj_ihlalde_calmaz_ama_denemede_calar(test_ayarlari, baglanti):
    yonetici = AnonsYoneticisi(test_ayarlari)
    sayan = _SayanAnonscu()
    yonetici._anonscu = sayan
    mesaj = dict(_mesaj(baglanti), enabled=0)

    assert yonetici.duyur(kamera_id=1, zaman_s=100.0, mesaj=mesaj) is None
    assert not sayan.cagrilar
    # Deneme, kurulum doğrulamak içindir: kapalı mesajı da çalar
    assert yonetici.deneme(mesaj).basarili
    assert len(sayan.cagrilar) == 1


def test_deneme_cooldown_uygulamaz(test_ayarlari, baglanti):
    """Kullanıcı düğmeye iki kez basarsa iki kez duymalı."""
    yonetici = AnonsYoneticisi(test_ayarlari)
    sayan = _SayanAnonscu()
    yonetici._anonscu = sayan
    mesaj = _mesaj(baglanti)

    yonetici.deneme(mesaj)
    yonetici.deneme(mesaj)
    assert len(sayan.cagrilar) == 2


def test_null_anonscu_sonuc_dondurur():
    sonuc = NullAnonscu().cal("helmet", "deneme", None)
    assert not sonuc.basarili and sonuc.mesaj


# ---- panel ----


def test_anons_sayfasi_yontemi_ve_mesajlari_gosterir(istemci):
    sayfa = istemci.get("/anons").text
    assert "Anons yöntemi" in sayfa
    assert "kapalı" in sayfa
    assert "Lütfen baretinizi takınız." in sayfa  # seed mesajı
    assert "Deneme anonsu çal" in sayfa
    # Üç olasılığın da kurulumu anlatılıyor (docs/08 R3)
    assert "ANONS=ses_karti" in sayfa
    assert "ANONS=http" in sayfa


def test_deneme_dugmesi_sonucu_sayfada_gosterir(istemci, test_ayarlari):
    yanit = istemci.post("/anons/1/deneme", follow_redirects=True)
    assert yanit.status_code == 200
    assert "hiçbir ses çalınmadı" in yanit.text  # ANONS=null olduğu için dürüst cevap


def test_olmayan_mesajin_denemesi_reddedilir(istemci):
    assert istemci.post("/anons/9999/deneme").status_code == 400


def test_mesaj_duzenlenebilir(istemci, test_ayarlari):
    yanit = istemci.post(
        "/anons/1/kaydet",
        data={
            "metin": "Lütfen güvenli mesafeyi koruyunuz.",
            "ses_dosyasi": "veri/sesler/a.wav",
            "acik": "1",
        },
        follow_redirects=True,
    )
    assert yanit.status_code == 200
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute("SELECT * FROM announcement_messages WHERE id = 1").fetchone()
        assert satir["text"] == "Lütfen güvenli mesafeyi koruyunuz."
        assert satir["audio_file"] == "veri/sesler/a.wav"
        assert satir["enabled"] == 1
    finally:
        baglanti.close()


def test_bos_metin_reddedilir(istemci):
    yanit = istemci.post("/anons/1/kaydet", data={"metin": "   ", "acik": "1"})
    assert yanit.status_code == 400
