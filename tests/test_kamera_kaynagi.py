"""Kamera kaynağı: üç durum (bağlanıyor / çevrimiçi / çevrimdışı) ve bağlanamama
sebebinin Türkçe teşhisi. İş parçacığı başlatılmaz; zaman elle verilir."""

from __future__ import annotations

import socket

from app.analiz.kamera import (
    DURUM_BAGLANIYOR,
    DURUM_OFFLINE,
    DURUM_ONLINE,
    OFFLINE_ESIGI_SN,
    KameraKaynagi,
)


def _kaynak(tip="rtsp", url="rtsp://admin:x@10.0.0.5:554/ana") -> KameraKaynagi:
    kaynak = KameraKaynagi(1, "K1", tip, url)
    kaynak._baslangic = 1000.0  # baslat() çağrılmadan "şimdi başladı" say
    return kaynak


def test_yeni_kamera_ilk_dakika_baglaniyor_sayilir():
    """Yeni eklenen kameraya daha ilk kare gelmeden 'çevrimdışı' olayı düşmemeli."""
    kaynak = _kaynak()
    assert kaynak.durum(simdi=1000.0 + 5) == DURUM_BAGLANIYOR
    assert kaynak.durum(simdi=1000.0 + OFFLINE_ESIGI_SN - 1) == DURUM_BAGLANIYOR
    # süre doldu, hâlâ kare yok → artık gerçekten çevrimdışı
    assert kaynak.durum(simdi=1000.0 + OFFLINE_ESIGI_SN + 1) == DURUM_OFFLINE


def test_kare_gelince_online_kesilince_offline():
    kaynak = _kaynak()
    kaynak._son_kare_zamani = 1010.0
    assert kaynak.durum(simdi=1011.0) == DURUM_ONLINE
    assert kaynak.durum(simdi=1010.0 + OFFLINE_ESIGI_SN - 1) == DURUM_ONLINE
    assert kaynak.durum(simdi=1010.0 + OFFLINE_ESIGI_SN + 1) == DURUM_OFFLINE
    # bir kez kare geldiyse 'bağlanıyor' durumuna geri dönülmez
    assert kaynak.durum(simdi=1010.0 + OFFLINE_ESIGI_SN + 1) != DURUM_BAGLANIYOR


def test_olmayan_dosya_teshisi(tmp_path):
    kaynak = _kaynak("file", str(tmp_path / "yok.mp4"))
    assert kaynak._ac() is None
    assert "bulunamadı" in kaynak.son_hata
    assert kaynak.son_deneme_utc  # son deneme zamanı dolduruldu


def test_bozuk_dosya_teshisi(tmp_path):
    bozuk = tmp_path / "bozuk.mp4"
    bozuk.write_bytes(b"bu bir video degil")
    kaynak = _kaynak("file", str(bozuk))
    assert kaynak._ac() is None
    assert "açılamadı" in kaynak.son_hata


def test_ulasilamayan_kamera_teshisi():
    # Boş bir yerel port: bağlantı anında reddedilir → "ulaşılamıyor" mesajı
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    kaynak = _kaynak("rtsp", f"rtsp://admin:x@127.0.0.1:{port}/ana")
    assert kaynak._ac() is None
    assert "ulaşılamıyor" in kaynak.son_hata
    assert f"127.0.0.1:{port}" in kaynak.son_hata
    assert "admin" not in kaynak.son_hata  # kimlik bilgisi mesaja sızmaz


def test_bozuk_rtsp_adresi_teshisi():
    kaynak = _kaynak("rtsp", "rtsp://")
    assert kaynak._ac() is None
    assert "çözümlenemedi" in kaynak.son_hata
