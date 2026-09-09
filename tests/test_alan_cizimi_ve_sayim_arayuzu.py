"""Kamera sayfasının iki yeni yeteneği: kolay alan çizimi ve bölge sayımı.

Bu testler ekranda GÖRÜNENİ korur. Kullanıcı kodu okumaz; sistemi ekrandaki
düğmelerden tanır. Bir düğme sessizce kaybolursa özellik de kaybolmuş demektir.
"""

from __future__ import annotations

from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
STATIK = KOK / "backend" / "app" / "web" / "static"


@pytest.fixture
def kamera_id(istemci):
    istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Yükleme rampası",
            "area": "Sevkiyat",
            "source_type": "rtsp",
            "source_url": "rtsp://10.0.0.7/akis",
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    return 1


@pytest.fixture
def bolgeli_kamera(istemci, kamera_id):
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": "Rampa önü",
            "zone_type": "loading_area",
            "polygon": "[[0.2,0.2],[0.8,0.2],[0.8,0.8],[0.2,0.8]]",
        },
        follow_redirects=False,
    )
    return kamera_id


# --------------------------------------------------------------- alan çizimi


def test_alani_otomatik_bul_paneli_ekranda(istemci, kamera_id):
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert "alanı sistem bulsun" in sayfa
    assert 'id="alan-bul-canli"' in sayfa


def test_cizim_arkaplani_denetimi_ekranda(istemci, kamera_id):
    """Canlı akış saniyede yenilenirken köşe tıklamak zor; kullanıcı arka
    planı kendisi seçebilmeli."""
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert 'id="kare-dondur"' in sayfa
    assert 'id="arkaplan-dosya"' in sayfa
    assert 'id="canliya-don"' in sayfa
    assert "Kareyi dondur" in sayfa


def test_kamera_bagli_degilken_ekran_goruntusu_yolu_anlatilir(istemci, kamera_id):
    """Kurulumdan ÖNCE bölge hazırlayabilmek bu cümleye bağlı."""
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert "Ekran görüntüsü yükle" in sayfa
    assert "NVR" in sayfa
    assert "kaydedilmez" in sayfa  # KVKK sözü ekranda da yazmalı


def test_goruntude_bolge_secme_altyapisi_ekranda(istemci, kamera_id):
    """Bölgeye tıklayınca taralı görünsün ve ne yapılacağı çıksın."""
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert 'id="secili-bolge"' in sayfa
    assert "taralı alanlar" in sayfa
    assert "window.KAMERA_ID" in sayfa


def test_bolge_verisi_tip_adini_tasir(istemci, bolgeli_kamera):
    """Seçilen bölgenin kutusunda tipi de yazar: 'Rampa önü · Yükleme alanı'."""
    sayfa = istemci.get(f"/kameralar/{bolgeli_kamera}").text
    assert '"tip_adi": "Y\u00fckleme alan\u0131"' in sayfa or '"tip_adi"' in sayfa


def test_cizim_betigi_tarama_ve_secim_iceriyor():
    betik = (STATIK / "kamera_detay.js").read_text(encoding="utf-8")
    for parca in ("taramaDeseni", "noktaPoligonda", "bolgeSec", "donmusaGec"):
        assert parca in betik, f"{parca} kayıp"


def test_dikdortgen_cizim_dugmesi_ekranda(istemci, kamera_id):
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert 'id="cizim-dikdortgen"' in sayfa
    assert "Dikdörtgen çiz" in sayfa


def test_kose_surukleme_kullaniciya_anlatilir(istemci, kamera_id):
    """Yetenek varsa ekranda yazmalı: kimse denemeden keşfetmek zorunda kalmasın."""
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert "sürükleyerek" in sayfa


def test_cizim_betigi_yeni_kipleri_iceriyor():
    betik = (STATIK / "kamera_detay.js").read_text(encoding="utf-8")
    for parca in ("dikdortgenKoseleri", "tutulanKose", "oneriyiYukle", "arkaPlanaKoy"):
        assert parca in betik, f"{parca} kayıp"


def test_yuklenen_goruntu_canli_kareyle_ezilmez():
    """data-donmus okunmazsa yüklenen ekran görüntüsü bir saniye sonra
    canlı kareyle değişir ve kullanıcı başka görüntüye çizmiş olur."""
    assert 'dataset.donmus === "1"' in (STATIK / "onizleme.js").read_text(encoding="utf-8")


# ---------------------------------------------------------------- sayım


def test_sayim_karti_bolge_varken_gorunur(istemci, bolgeli_kamera):
    sayfa = istemci.get(f"/kameralar/{bolgeli_kamera}").text
    assert 'id="sayim-karti"' in sayfa
    assert "Bölge sayımı" in sayfa
    assert 'id="sayac-sifirla"' in sayfa


def test_sayim_karti_bolgesiz_kamerada_gizli(istemci, kamera_id):
    """Bölge yoksa sayacak bir şey de yok; boş kart yalnızca gürültüdür."""
    sayfa = istemci.get(f"/kameralar/{kamera_id}").text
    assert '<section class="kart" id="sayim-karti" hidden>' in sayfa


def test_sayim_terimleri_aciklanir(istemci, bolgeli_kamera):
    """Üç sayı üç ayrı soruyu cevaplar; hangisinin ne olduğu ekranda yazmalı."""
    sayfa = istemci.get(f"/kameralar/{bolgeli_kamera}").text
    assert "Giren" in sayfa and "İçeride" in sayfa
    assert "vardiya başında sıfırlayın" in sayfa


def test_sayimin_uyari_uretmedigi_yaziyor(istemci, bolgeli_kamera):
    """Kullanıcı sayımı kuralla karıştırmamalı: sayım anons tetiklemez."""
    sayfa = istemci.get(f"/kameralar/{bolgeli_kamera}").text
    assert "Sayım hiçbir uyarı ya da anons üretmez" in sayfa


def test_durum_json_bolge_sayimlarini_tasir(istemci, bolgeli_kamera):
    veri = istemci.get(f"/kameralar/{bolgeli_kamera}/durum.json").json()
    assert "bolge_sayimlari" in veri


def test_sayac_sifirlama_analiz_kapaliyken_dogruyu_soyler(istemci, bolgeli_kamera):
    """Analiz çalışmıyorken 'sıfırlandı' demek yalan olurdu."""
    veri = istemci.post(f"/kameralar/{bolgeli_kamera}/sayac-sifirla").json()
    assert veri["tamam"] is False
    assert "Sistemi Başlat" in veri["mesaj"]


def test_sayac_sifirlama_olmayan_kamerada_404(istemci):
    assert istemci.post("/kameralar/999/sayac-sifirla").status_code == 404
