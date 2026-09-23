"""Olay kodu, önem ve bitiş veritabanında (docs/17 §6.1, §6.3; Faz 2c-2).

Sınanan: yazıcı kodu ve önemi yazar; anlık olayın bitişi başlangıcıdır;
"Kamera çevrimdışı" açık doğar ve kamera dönünce, kapatılınca ya da silinince
kapanır; süreç açılırken ve kapanırken açık olay kalmaz; model yüklenemeyince
iki yoldan da olay yazılır. Kamera, model ve iş parçacığı yoktur.
"""

from __future__ import annotations

import ast
import dataclasses
import json
from pathlib import Path

import pytest

from app import veritabani, zaman
from app.analiz.kamera import DURUM_BITTI, DURUM_OFFLINE, DURUM_ONLINE
from app.analiz.supervizor import AnalizSupervizoru
from app.olaylar.yazici import (
    acik_olaylari_kapat,
    ihlal_yaz,
    olay_kapat,
    sistem_olayi_yaz,
)
from app.rules.olay_kodu import OLAY_KODLARI
from app.rules.tipler import Ihlal

UYGULAMA = Path(__file__).resolve().parents[1] / "backend" / "app"


@pytest.fixture
def baglanti(test_ayarlari):
    bag = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(bag)
    simdi = zaman.simdi_utc()
    bag.execute(
        "INSERT INTO cameras (id, name, source_type, source_url, sample_fps, created_at, "
        "updated_at) VALUES (1, 'Rampa', 'rtsp', 'rtsp://x', 6, ?, ?)",
        (simdi, simdi),
    )
    bag.commit()
    yield bag
    bag.close()


def _olay(baglanti, olay_id: int) -> dict:
    satir = dict(baglanti.execute("SELECT * FROM events WHERE id = ?", (olay_id,)).fetchone())
    satir["detaylar"] = json.loads(satir["details"])
    return satir


def _kodlar(baglanti) -> list[str]:
    return [s[0] for s in baglanti.execute("SELECT event_code FROM events ORDER BY id")]


# ------------------------------------------------------------------ yazıcı


def test_ihlal_kodu_onemi_ve_anlik_bitisi_yazilir(baglanti, test_ayarlari):
    ihlal = Ihlal(1, 1, [5], None, 2.0, {"sinif": "person"}, kod="RESTRICTED_ENTRY", onem="high")
    olay = _olay(baglanti, ihlal_yaz(baglanti, test_ayarlari, ihlal, {"id": 1}, None))
    assert (olay["event_code"], olay["severity"]) == ("RESTRICTED_ENTRY", "high")
    # Yaşam döngüsü (2c-3) gelene kadar ihlal anlıktır: "sürüyor" görünmez
    assert olay["resolved_at"] == olay["occurred_at"]


def test_kodsuz_ihlal_eski_olay_gibi_yazilir(baglanti, test_ayarlari):
    olay_id = ihlal_yaz(baglanti, test_ayarlari, Ihlal(1, 1, [5], None, 2.0), {}, None)
    olay = _olay(baglanti, olay_id)
    assert olay["event_code"] is None and olay["severity"] is None


def test_kamera_cevrimdisi_acik_dogar_disk_uyarisi_anliktir(baglanti):
    kopuk = _olay(
        baglanti, sistem_olayi_yaz(baglanti, "Kamera çevrimdışı: Rampa", 1, kod="CAMERA_DOWN")
    )
    disk = _olay(baglanti, sistem_olayi_yaz(baglanti, "Disk azalıyor", kod="DISK_LOW"))
    assert (kopuk["event_code"], kopuk["severity"], kopuk["resolved_at"]) == (
        "CAMERA_DOWN",
        "system",
        None,
    )
    assert disk["resolved_at"] == disk["occurred_at"]


def test_olay_kapat_bir_kez_kapatir_ve_sebebi_yazar(baglanti):
    olay_id = sistem_olayi_yaz(
        baglanti, "Kamera çevrimdışı: Rampa", 1, {"ek": 1}, kod="CAMERA_DOWN"
    )
    assert olay_kapat(baglanti, olay_id, "kosul_bitti") is True
    assert olay_kapat(baglanti, olay_id, "kapanis") is False  # ikinci kapanış yok
    olay = _olay(baglanti, olay_id)
    assert olay["resolved_at"] is not None
    assert olay["detaylar"] == {
        "mesaj": "Kamera çevrimdışı: Rampa",
        "ek": 1,
        "kapanis_sebebi": "kosul_bitti",
    }


def test_bitis_baslangictan_once_yazilmaz(baglanti):
    """Duvar saati geri alınsa da (NTP) süre eksiye düşmez."""
    olay_id = sistem_olayi_yaz(baglanti, "Kamera çevrimdışı", 1, kod="CAMERA_DOWN")
    olay_kapat(baglanti, olay_id, "kosul_bitti", zaman.saniye_once_utc(3600))
    olay = _olay(baglanti, olay_id)
    assert olay["resolved_at"] == olay["occurred_at"]


def test_bozuk_ayrintili_acik_olay_da_kapanir(baglanti):
    """Elle bozulmuş bir satır, açılıştaki toplu kapanışı durdurmamalı."""
    olay_id = sistem_olayi_yaz(baglanti, "Kamera çevrimdışı", 1, kod="CAMERA_DOWN")
    baglanti.execute("UPDATE events SET details = '{bozuk' WHERE id = ?", (olay_id,))
    baglanti.commit()
    assert acik_olaylari_kapat(baglanti, "yeniden_baslama") == 1
    olay = _olay(baglanti, olay_id)
    assert olay["detaylar"] == {"ham": "{bozuk", "kapanis_sebebi": "yeniden_baslama"}


def test_her_sistem_olayi_cagrisi_bilinen_bir_kod_verir():
    """Ürün kodundaki her sistem olayı çağrısı sözlükteki bir SİSTEM kodunu
    yazıyla verir (yazım hatası olay kaybettirmesin, ekranda adsız kalmasın)."""
    cagrilar: list[tuple[str, str, object]] = []

    class _Gezgin(ast.NodeVisitor):
        def __init__(self, dosya: str) -> None:
            self.dosya, self.fonksiyon = dosya, ""

        def visit_FunctionDef(self, dugum):
            onceki, self.fonksiyon = self.fonksiyon, dugum.name
            self.generic_visit(dugum)
            self.fonksiyon = onceki

        def visit_Call(self, dugum):
            ad = getattr(dugum.func, "id", None) or getattr(dugum.func, "attr", None)
            if ad in ("sistem_olayi_yaz", "_sistem_olayi"):
                kod = next((k.value for k in dugum.keywords if k.arg == "kod"), None)
                cagrilar.append((self.dosya, self.fonksiyon, kod))
            self.generic_visit(dugum)

    for dosya in UYGULAMA.rglob("*.py"):
        _Gezgin(dosya.name).visit(ast.parse(dosya.read_text(encoding="utf-8")))

    assert len(cagrilar) >= 10
    for dosya, fonksiyon, kod in cagrilar:
        if isinstance(kod, ast.Name) and fonksiyon == "_sistem_olayi":
            continue  # yardımcının kendi aktarımı
        assert isinstance(kod, ast.Constant), (dosya, fonksiyon)
        assert kod.value in OLAY_KODLARI and OLAY_KODLARI[kod.value].sistem_mi, kod.value


# ------------------------------------------------------------------ süpervizör


class _SahteKaynak:
    def __init__(self):
        self.hal = DURUM_OFFLINE
        self.akis_sn = 0.0
        self.son_hata = ""
        self.olculen_fps = 6.0
        self.durduruldu = False

    def durum(self):
        return self.hal

    def kesintisiz_akis_sn(self):
        return self.akis_sn

    def durdur(self):
        self.durduruldu = True


@pytest.fixture
def supervizor(test_ayarlari, baglanti):
    sup = AnalizSupervizoru(dataclasses.replace(test_ayarlari, kamera_up_kararlilik_sn=5.0))
    kaynak = _SahteKaynak()
    sup._kaynaklar = {1: kaynak}
    sup._kamera_konfig = {1: {"name": "Rampa", "sample_fps": 6}}
    sup._son_durumlar = {1: DURUM_ONLINE}
    return sup, kaynak


def test_kamera_donunce_cevrimdisi_olayi_kapanir(supervizor, baglanti):
    sup, kaynak = supervizor
    kaynak.hal = DURUM_OFFLINE
    sup._durumlari_yaz(baglanti)
    (kopuk_id,) = [s[0] for s in baglanti.execute("SELECT id FROM events")]
    assert _olay(baglanti, kopuk_id)["resolved_at"] is None  # sürüyor
    # Kopukluk bir dakika önce başlamış olsun (test saniyeler içinde biter)
    baglanti.execute(
        "UPDATE events SET occurred_at = ? WHERE id = ?", (zaman.saniye_once_utc(60), kopuk_id)
    )

    kaynak.hal, kaynak.akis_sn = DURUM_ONLINE, 7.0
    sup._durumlari_yaz(baglanti)
    assert _kodlar(baglanti) == ["CAMERA_DOWN", "CAMERA_UP"]
    kopuk = _olay(baglanti, kopuk_id)
    assert kopuk["detaylar"]["kapanis_sebebi"] == "kosul_bitti"
    # Bitiş, görüntünün geri geldiği an: "tekrar çevrimiçi" yazıldığı andan önce
    donus = baglanti.execute("SELECT occurred_at FROM events WHERE event_code = 'CAMERA_UP'")
    assert kopuk["occurred_at"] <= kopuk["resolved_at"] < donus.fetchone()[0]


def test_video_bitince_acik_kopukluk_kapanir(supervizor, baglanti):
    sup, kaynak = supervizor
    kaynak.hal = DURUM_OFFLINE
    sup._durumlari_yaz(baglanti)
    kaynak.hal = DURUM_BITTI
    sup._durumlari_yaz(baglanti)
    assert _kodlar(baglanti) == ["CAMERA_DOWN", "VIDEO_FINISHED"]
    assert (
        baglanti.execute("SELECT COUNT(*) FROM events WHERE resolved_at IS NULL").fetchone()[0] == 0
    )


def test_silinen_kameranin_acik_olayi_kapanir(supervizor, baglanti):
    """Kamera silinince olayın camera_id'si boşalır (FK SET NULL); olay yine de
    id'sinden bulunup kapanır, "sürüyor" diye asılı kalmaz."""
    sup, kaynak = supervizor
    kaynak.hal = DURUM_OFFLINE
    sup._durumlari_yaz(baglanti)
    baglanti.execute("DELETE FROM cameras WHERE id = 1")
    baglanti.commit()
    sup._konfigurasyonu_yenile(baglanti)
    assert kaynak.durduruldu
    (satir,) = baglanti.execute("SELECT camera_id, resolved_at, details FROM events").fetchall()
    assert satir["camera_id"] is None and satir["resolved_at"] is not None
    assert json.loads(satir["details"])["kapanis_sebebi"] == "kamera_degisti"


def test_acilista_acik_olay_kapanir_ve_duzgun_kapanmama_soylenir(test_ayarlari, baglanti):
    sistem_olayi_yaz(baglanti, "Sistem başladı", kod="SYSTEM_STARTED")  # "durdu" hiç yazılmadı
    asili = sistem_olayi_yaz(baglanti, "Kamera çevrimdışı: Rampa", 1, kod="CAMERA_DOWN")

    AnalizSupervizoru(test_ayarlari)._acilis_olaylarini_yaz(baglanti)

    assert _olay(baglanti, asili)["detaylar"]["kapanis_sebebi"] == "yeniden_baslama"
    son = _olay(baglanti, baglanti.execute("SELECT MAX(id) FROM events").fetchone()[0])
    assert son["event_code"] == "SYSTEM_STARTED"
    assert "düzgün kapanmamıştı" in son["detaylar"]["mesaj"]
    assert son["detaylar"]["kapatilan_acik_olay"] == 1


def test_duzgun_kapanistan_sonra_acilis_sade_yazilir(test_ayarlari, baglanti):
    sup = AnalizSupervizoru(test_ayarlari)
    sup._acilis_olaylarini_yaz(baglanti)
    sup._kapanis_olaylarini_yaz(baglanti)
    sup._acilis_olaylarini_yaz(baglanti)
    mesajlar = [json.loads(s[0])["mesaj"] for s in baglanti.execute("SELECT details FROM events")]
    assert mesajlar == ["Sistem başladı", "Sistem durdu", "Sistem başladı"]


def test_analiz_dongusu_yasamini_olay_olarak_yazar(test_ayarlari, baglanti):
    """Açılış → beklenmeyen model hatası → kapanış: üçü de Olaylar'da görünür.
    Eskiden beklenmeyen hata yolu olay yazmıyordu (docs/17 §6.1)."""
    sup = AnalizSupervizoru(test_ayarlari)
    acik = sistem_olayi_yaz(baglanti, "Kamera çevrimdışı: Rampa", 1, kod="CAMERA_DOWN")

    def _coken(_baglanti):
        raise RuntimeError("beklenmeyen hata")

    sup._tespitciyi_kur = _coken
    sup._dur.set()  # döngü hiç dönmeden kapanışa gitsin
    sup._dongu()

    assert _kodlar(baglanti) == [
        "CAMERA_DOWN",
        "SYSTEM_STARTED",
        "MODEL_LOAD_FAILED",
        "SYSTEM_STOPPED",
    ]
    assert _olay(baglanti, acik)["detaylar"]["kapanis_sebebi"] == "yeniden_baslama"
    assert (
        baglanti.execute("SELECT COUNT(*) FROM events WHERE resolved_at IS NULL").fetchone()[0] == 0
    )


def test_olay_yazilamazsa_model_atilmaz(test_ayarlari, baglanti, monkeypatch):
    """GPU → CPU uyarısı yazılırken veritabanı kilitliyse tespitçi yine kurulur."""
    import sqlite3

    from app.analiz import supervizor as supervizor_modulu

    class _Tespitci:
        cihaz_uyarisi = "GPU istendi, CPU kullanılıyor"

        def __init__(self, *a, **k):
            pass

    def _kilitli(*a, **k):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(supervizor_modulu, "Tespitci", _Tespitci)
    monkeypatch.setattr(supervizor_modulu, "sistem_olayi_yaz", _kilitli)
    sup = AnalizSupervizoru(test_ayarlari)
    sup._modeli_hazirla = lambda: None
    sup._tespitciyi_kur(baglanti)
    assert isinstance(sup.tespitci, _Tespitci)
    assert sup.model_durumu == "hazir"


def test_acik_canli_akis_varken_kapanis_biter_ve_sistem_durdu_yazilir(test_ayarlari):
    """Gerçek sunucu: tarayıcıda Olaylar açıkken (SSE) sistem durdurulur.

    Kapanış süresi verilmeden uvicorn akışı sonsuza kadar bekliyordu; ölçüldü:
    30 sn sonra hâlâ kapanmamıştı. Panelin verdiği süreyle kapanış biter,
    uygulamanın kapanış kodu çalışır ve "Sistem durdu" olayı yazılır.
    """
    import re
    import socket
    import threading
    import time

    import uvicorn

    from app.uygulama import uygulama_olustur

    baslatici = (UYGULAMA.parents[1] / "masaustu" / "dalsan_launcher.py").read_text(
        encoding="utf-8"
    )
    sure = int(re.search(r"^KAPANIS_BEKLEME_SN = (\d+)$", baslatici, re.M).group(1))

    with socket.socket() as bos:
        bos.bind(("127.0.0.1", 0))
        port = bos.getsockname()[1]
    sunucu = uvicorn.Server(
        uvicorn.Config(
            uygulama_olustur(test_ayarlari, analiz=True),
            host="127.0.0.1",
            port=port,
            log_config=None,
            timeout_graceful_shutdown=sure,
        )
    )
    is_parcacigi = threading.Thread(target=sunucu.run, daemon=True)
    is_parcacigi.start()
    for _ in range(200):
        if sunucu.started:
            break
        time.sleep(0.05)
    assert sunucu.started

    with socket.create_connection(("127.0.0.1", port), timeout=5) as akis:
        akis.sendall(b"GET /olaylar/akis HTTP/1.1\r\nHost: 127.0.0.1\r\n\r\n")
        basliklar = akis.recv(4096)
        assert b" 200 " in basliklar and b"text/event-stream" in basliklar  # akış açık

        baslangic = time.monotonic()
        sunucu.should_exit = True
        is_parcacigi.join(timeout=sure + 10)
        gecen = time.monotonic() - baslangic
    assert not is_parcacigi.is_alive(), "açık akış kapanışı bekletiyor"
    assert gecen < sure + 5

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kodlar = [s[0] for s in baglanti.execute("SELECT event_code FROM events ORDER BY id")]
    finally:
        baglanti.close()
    assert kodlar[0] == "SYSTEM_STARTED" and kodlar[-1] == "SYSTEM_STOPPED"
