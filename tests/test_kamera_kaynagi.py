"""Kamera kaynağı: üç durum (bağlanıyor / çevrimiçi / çevrimdışı) ve bağlanamama
sebebinin Türkçe teşhisi. İş parçacığı başlatılmaz; zaman elle verilir."""

from __future__ import annotations

import socket

from app.analiz.kamera import (
    DURUM_BAGLANIYOR,
    DURUM_OFFLINE,
    DURUM_ONLINE,
    ILK_BAGLANTI_TOLERANSI_SN,
    VARSAYILAN_KOPUK_ESIGI_SN,
    KameraKaynagi,
)


def _kaynak(tip="rtsp", url="rtsp://admin:x@10.0.0.5:554/ana", **ek) -> KameraKaynagi:
    kaynak = KameraKaynagi(1, "K1", tip, url, **ek)
    kaynak._baslangic = 1000.0  # baslat() çağrılmadan "şimdi başladı" say
    return kaynak


def test_iki_sure_ayri():
    """İlk bağlantı yavaştır (60 sn tolerans); akan görüntünün kesilmesi ise
    çabuk fark edilmeli (docs/17 K8). Eskiden ikisi de 60 sn'ydi: kopan bir
    kamera bir dakika boyunca 'çevrimiçi' görünüyordu."""
    assert ILK_BAGLANTI_TOLERANSI_SN == 60.0
    assert VARSAYILAN_KOPUK_ESIGI_SN == 10.0


def test_yeni_kamera_ilk_dakika_baglaniyor_sayilir():
    """Yeni eklenen kameraya daha ilk kare gelmeden 'çevrimdışı' olayı düşmemeli."""
    kaynak = _kaynak()
    assert kaynak.durum(simdi=1000.0 + 5) == DURUM_BAGLANIYOR
    # Kopukluk eşiğini (10 sn) geçmek ilk bağlantıda çevrimdışı demek DEĞİL
    assert kaynak.durum(simdi=1000.0 + VARSAYILAN_KOPUK_ESIGI_SN + 5) == DURUM_BAGLANIYOR
    assert kaynak.durum(simdi=1000.0 + ILK_BAGLANTI_TOLERANSI_SN - 1) == DURUM_BAGLANIYOR
    # süre doldu, hâlâ kare yok → artık gerçekten çevrimdışı
    assert kaynak.durum(simdi=1000.0 + ILK_BAGLANTI_TOLERANSI_SN + 1) == DURUM_OFFLINE


def test_kare_gelince_online_kesilince_kopukluk_esiginde_offline():
    kaynak = _kaynak()
    kaynak._son_kare_zamani = 1010.0
    assert kaynak.durum(simdi=1011.0) == DURUM_ONLINE
    assert kaynak.durum(simdi=1010.0 + VARSAYILAN_KOPUK_ESIGI_SN - 1) == DURUM_ONLINE
    assert kaynak.durum(simdi=1010.0 + VARSAYILAN_KOPUK_ESIGI_SN + 1) == DURUM_OFFLINE
    # bir kez kare geldiyse 'bağlanıyor' durumuna geri dönülmez
    assert kaynak.durum(simdi=1010.0 + VARSAYILAN_KOPUK_ESIGI_SN + 1) != DURUM_BAGLANIYOR


def test_kopukluk_esigi_ayardan_gelir():
    kaynak = _kaynak(kopuk_esigi_sn=30.0)
    kaynak._son_kare_zamani = 1010.0
    assert kaynak.durum(simdi=1010.0 + 20) == DURUM_ONLINE
    assert kaynak.durum(simdi=1010.0 + 31) == DURUM_OFFLINE


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


# ---------------------------------------------------------------------------
# Tek geçişlik video (şema 006 + web/videolar.py)
#
# Yüklenen bir test videosunun bir SONU vardır; kameranın yoktur. Bu ayrımın
# kod tarafındaki karşılığı `dongu` bayrağıdır ve aşağıdaki testler onun
# gerçekten çalıştığını GERÇEK bir video dosyasıyla ölçer — sahte bir
# VideoCapture ile değil, çünkü ölçülmek istenen tam olarak OpenCV'nin dosya
# sonunda ne yaptığıdır.
# ---------------------------------------------------------------------------


def _kisa_video(yol, kare_sayisi=5):
    """Birkaç karelik gerçek bir .mp4 üretir; üretilemezse None döner."""
    import cv2
    import numpy as np

    yazici = cv2.VideoWriter(str(yol), cv2.VideoWriter_fourcc(*"mp4v"), 25.0, (64, 48))
    if not yazici.isOpened():
        return None
    for numara in range(kare_sayisi):
        kare = np.full((48, 64, 3), numara * 20 % 255, dtype=np.uint8)
        yazici.write(kare)
    yazici.release()
    return yol if yol.is_file() and yol.stat().st_size > 0 else None


def test_tek_gecislik_video_bitince_durur(tmp_path):
    """Video sonuna gelince durum 'finished' olur, iş parçacığı sonlanır."""
    import pytest

    from app.analiz.kamera import DURUM_BITTI

    video = _kisa_video(tmp_path / "kisa.mp4")
    if video is None:
        pytest.skip("Bu ortamda OpenCV .mp4 yazamıyor (video kodlayıcı yok).")

    kaynak = KameraKaynagi(1, "Test videosu", "file", str(video), dongu=False)
    kaynak.baslat()
    kaynak._is_parcacigi.join(timeout=30)

    assert not kaynak._is_parcacigi.is_alive(), "video bitti ama iş parçacığı sürüyor"
    assert kaynak.bitti
    assert kaynak.durum() == DURUM_BITTI
    # Hata YOK: video planlandığı gibi bitti, düzeltilecek bir arıza değil.
    assert kaynak.son_hata == ""
    # Son kare elde kalır: kullanıcı bölge çizmek için görüntüye bakabilmeli.
    kare, _ = kaynak.son_kare()
    assert kare is not None


def test_dongu_kipinde_video_basa_sarar(tmp_path):
    """Varsayılan kip: video biter, başa sarar, kamera 'çevrimiçi' kalır."""
    import pytest

    video = _kisa_video(tmp_path / "kisa.mp4")
    if video is None:
        pytest.skip("Bu ortamda OpenCV .mp4 yazamıyor (video kodlayıcı yok).")

    kaynak = KameraKaynagi(2, "Döngü videosu", "file", str(video), dongu=True)
    kaynak.baslat()
    try:
        kaynak._is_parcacigi.join(timeout=3)
        assert kaynak._is_parcacigi.is_alive(), "döngü kipinde iş parçacığı durmamalı"
        assert not kaynak.bitti
        assert kaynak.durum() == DURUM_ONLINE
    finally:
        kaynak.durdur()


def test_rtsp_icin_tek_gecis_istenemez():
    """Bir RTSP akışının 'sonu' yoktur; kopması ayrı bir şeydir.

    `dongu=False` bir RTSP kaynağına uygulansaydı, ilk kopmada kamera
    'analiz tamamlandı' diye gösterilir ve bir daha hiç bağlanılmazdı.
    """
    kaynak = KameraKaynagi(3, "K", "rtsp", "rtsp://10.0.0.5/ana", dongu=False)
    assert kaynak.dongu is True


def test_bozuk_dosya_bitti_sayilmaz(tmp_path):
    """Hiç kare gelmeden okuma başarısızsa dosya BOZUKtur, video bitmiş değil.

    'Analiz tamamlandı' demek, kullanıcının boş olay listesine bakıp
    'demek ki videoda ihlal yokmuş' diye düşünmesine yol açardı.
    """
    bozuk = tmp_path / "bozuk.mp4"
    bozuk.write_bytes(b"bu bir video degil")
    kaynak = KameraKaynagi(4, "Bozuk", "file", str(bozuk), dongu=False)
    kaynak._dur.set()  # tek tur dönsün, sonsuza kadar yeniden denemesin
    kaynak._dongu()
    assert not kaynak.bitti
