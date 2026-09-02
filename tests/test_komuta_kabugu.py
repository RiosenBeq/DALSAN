"""Komuta kabuğu: altı ekranın ortak çerçevesi.

Bu aşamada ekran İÇERİKLERİ yok; testler kabuğun her ekranda açıldığını,
raftan hiçbir sayfanın ULAŞILAMAZ kalmadığını ve başlıktaki sayıların
tasarımın örnek değerleri değil GERÇEK veritabanı sayıları olduğunu korur.
"""

from __future__ import annotations

import pytest

from app import zaman

EKRANLAR = {
    "/komuta": "Komuta ekranı",
    "/komuta/duvar": "Canlı duvar",
    "/komuta/inceleme": "Olay inceleme",
    "/komuta/saglik": "Kamera sağlığı",
    "/komuta/uyari": "Uyarı ve anons",
    "/komuta/anons": "Anons sistemi",
}


@pytest.mark.parametrize(("yol", "baslik"), sorted(EKRANLAR.items()))
def test_her_komuta_ekrani_aciliyor(istemci, yol, baslik):
    yanit = istemci.get(yol)
    assert yanit.status_code == 200, yol
    assert baslik in yanit.text


@pytest.mark.parametrize("yol", sorted(EKRANLAR))
def test_her_ekranda_kabuk_ogeleri_var(istemci, yol):
    metin = istemci.get(yol).text
    # sol raf + üst başlık + içerik alanı
    assert 'class="komuta-raf"' in metin
    assert 'class="komuta-baslik"' in metin
    assert 'class="komuta-icerik"' in metin
    assert "/static/komuta.css?v=" in metin
    # rafın altı komuta düğmesi
    for hedef in EKRANLAR:
        assert f'href="{hedef}"' in metin, f"{yol} → raf bağlantısı eksik: {hedef}"


@pytest.mark.parametrize("yol", sorted(EKRANLAR))
def test_kurulum_sayfalari_raftan_ulasilabilir(istemci, yol):
    """Kameralar/Kurallar/KKD rafta olmazsa bölge çizimine erişim KAPANIR."""
    metin = istemci.get(yol).text
    for hedef in ("/kameralar", "/kurallar", "/kkd"):
        assert f'href="{hedef}"' in metin, f"{yol} → rafta {hedef} yok"


def test_aktif_raf_dugmesi_vurgulanir(istemci):
    metin = istemci.get("/komuta/saglik").text
    assert 'class="raf-dugme aktif" href="/komuta/saglik"' in metin
    assert 'class="raf-dugme " href="/komuta"' in metin


def test_eski_kabuktan_komutaya_donuluyor(istemci):
    """Kameralar sayfası eski kabukta açılır; oradan geri dönüş olmalı."""
    for yol in ("/kameralar", "/kurallar", "/kkd", "/"):
        assert '<a href="/komuta">← Komuta</a>' in istemci.get(yol).text, yol


def test_baslikta_sahte_sayi_yok(istemci):
    """Tasarımın örnek sayıları (24 kamera, 6 bölüm, 7 bölge) ekrana sızmamalı."""
    for yol in EKRANLAR:
        metin = istemci.get(yol).text
        for sahte in ("24 kamera", "6 bölüm", "7 bölge", "Vardiya 08:00"):
            assert sahte not in metin, f"{yol} → tasarımdan sahte veri: {sahte}"


def test_kamerasiz_kurulumda_ogretici_bos_durum(istemci):
    """Kamera yokken yeşil 'her şey yolunda' rozeti gösterilmez."""
    metin = istemci.get("/komuta").text
    assert "Henüz kamera eklenmedi" in metin
    assert "Canlı kamera" not in metin


def test_baslik_gercek_kamera_sayisini_gosteriyor(istemci):
    istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Sevkiyat Rampası",
            "area": "Sevkiyat",
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.5:554/1",
            "sample_fps": "6",
        },
    )
    metin = istemci.get("/komuta").text
    assert "1 bölüm · 1 kamera" in metin
    # Kamera var ama henüz bağlanmadı: sarı hap, uydurulmuş "canlı" yok
    assert "Canlı kamera 0 / 1" in metin


def test_anons_alt_basligi_gercek_ayardan_geliyor(istemci):
    """Tasarımdaki 'IP hoparlör · 7 bölge' yerine .env'deki gerçek anons yolu."""
    metin = istemci.get("/komuta/anons").text
    # test ayarlarında ANONS = null → "kapalı"; 5 hazır mesaj şemadan gelir
    assert "Anons yolu: kapalı · 5 hazır mesaj" in metin


def test_saat_saniyesiz_gosteriliyor():
    assert zaman.ekranda_goster_kisa("2026-09-02T12:42:07+00:00") == "02.09.2026 15:42"
    assert zaman.ekranda_tarih("2026-09-02T12:42:07+00:00") == "02.09.2026"


def test_ana_sayfa_eski_kabukta_kaldi(istemci):
    """'/' bu aşamada DEĞİŞMEDİ: teşhis ekranı yerinde duruyor."""
    metin = istemci.get("/").text
    assert "Aktif ayarlar" in metin
    assert 'class="komuta-raf"' not in metin
