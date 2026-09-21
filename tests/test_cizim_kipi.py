"""Kamera sayfasının sade / gelişmiş çizim kipi.

Sayfada yedi ayrı araç yaşıyor (dondur, görüntü yükle, otomatik bul, çiz,
dikdörtgen, geri al, kalibrasyon). Hepsi aynı anda ekrandayken ilk kez bölge
çizen biri hangisine basacağını seçemiyor; oysa bölge çizmek için üçü yetiyor.

Burada korunan iki şey var ve ikincisi daha önemlidir:

1. Sayfa SADE açılıyor ve gelişmiş araçlar gizleniyor.
2. Gizlenen araçlar DOM'DAN SİLİNMİYOR. Silinselerdi kamera_detay.js açılışta
   onları id ile arar, bulamaz ve sayfanın TAMAMI — çizim dahil — sessizce
   çalışmaz hale gelirdi. Bu, düzelttiğimiz sorundan çok daha kötüsü olurdu.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parents[1]
SABLON = KOK / "backend" / "app" / "web" / "templates" / "kamera_detay.html"
STIL = KOK / "backend" / "app" / "web" / "static" / "stil.css"
BETIK = KOK / "backend" / "app" / "web" / "static" / "cizim_kipi.js"

# Sade kipte gizlenmesi beklenenler ve DOM'da kalması ŞART olan id'ler.
GELISMIS_IDLER = ("arkaplan-secimi", "alan-bul")
# kamera_detay.js'in id ile aradığı, sade kipte de DOM'da durması gereken
# gelişmiş düğmeler. (Kalibrasyon kartı da gizlenir, düğmeleri buradadır.)
JS_ARADIGI_IDLER = (
    "kare-dondur",
    "arkaplan-dosya",
    "canliya-don",
    "alan-bul-canli",
    "alan-onerileri",
    "kalibrasyon-baslat",
    "kalibrasyon-noktalar",
    "kalibrasyon-kaydet",
    "image-points",
    "world-points",
)


@pytest.fixture(scope="module")
def sablon() -> str:
    return SABLON.read_text(encoding="utf-8")


def _kamera_ekle(istemci) -> int:
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "Kip Testi",
            "area": "",
            "source_type": "rtsp",
            "source_url": "rtsp://admin:x@10.0.0.9:554/ana",
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    return int(yanit.headers["location"].rsplit("/", 1)[1])


# ------------------------------------------------------------ sayfa gerçeği


def test_sayfa_sade_kipte_aciliyor(istemci):
    """Varsayılan sade: kullanıcı her an TEK bir sonraki hamle görmeli."""
    sayfa = istemci.get(f"/kameralar/{_kamera_ekle(istemci)}").text
    assert "kip-basit" in sayfa
    assert 'id="kip-anahtari"' in sayfa
    assert "Gelişmiş araçlar" in sayfa


def test_gelismis_araclar_gizlenir_ama_silinmez(istemci):
    """En kritik test: gizlemek silmek DEĞİLDİR.

    Silinselerdi kamera_detay.js bu id'leri bulamaz ve sayfanın tamamı —
    bölge çizimi dahil — sessizce çalışmaz hale gelirdi.
    """
    sayfa = istemci.get(f"/kameralar/{_kamera_ekle(istemci)}").text
    for eleman_id in GELISMIS_IDLER + JS_ARADIGI_IDLER:
        assert f'id="{eleman_id}"' in sayfa, f"{eleman_id} DOM'dan kaybolmuş"


def test_sade_kipte_bolge_cizmenin_kendisi_gizlenmez(istemci):
    """Sade kipte kalması GEREKENler: bölge çizmek bunlarsız yapılamaz."""
    sayfa = istemci.get(f"/kameralar/{_kamera_ekle(istemci)}").text
    for zorunlu in (
        "cizim-baslat",
        "cizim-dikdortgen",
        "cizim-geri",
        "cizim-temizle",
        "bolge-kaydet",
        "bolge-tipi",
    ):
        govde = _etiket_bul(sayfa, zorunlu)
        assert "data-gelismis" not in govde, f"{zorunlu} sade kipte gizlenmemeli"


def _etiket_bul(sayfa: str, eleman_id: str) -> str:
    """`id="..."` geçen etiketin açılış bölümü."""
    eslesme = re.search(r"<[^>]*id=\"" + re.escape(eleman_id) + r"\"[^>]*>", sayfa)
    assert eslesme, f"{eleman_id} sayfada yok"
    return eslesme.group(0)


# ------------------------------------------------------------ işaretleme


def test_gelismis_bolumler_isaretli(sablon):
    """Kalibrasyon kartı dahil dört bölüm gizlenmeli."""
    assert sablon.count("data-gelismis") >= 4
    assert '<section class="kart" data-gelismis>' in sablon


def test_kalibrasyon_gelismis_tarafta(sablon):
    """Mesafe kalibrasyonu, ilk bölgesini çizen kullanıcının işi değildir:
    yalnızca güvenli mesafe kuralı için gerekir (docs/03)."""
    # Başlığın kendisi aranır: "Mesafe kalibrasyonu" metni sayfada daha
    # yukarıda, bir açıklama cümlesinin içinde de geçiyor.
    konum = sablon.index("<h3>Mesafe kalibrasyonu")
    onceki_bolum = sablon.rindex("<section", 0, konum)
    assert "data-gelismis" in sablon[onceki_bolum:konum]


# ------------------------------------------------- gizleme nerede yapılıyor


def test_gizleme_css_ile_yapiliyor(sablon):
    """CSS ile gizlenmeli; JS ile DOM'dan çıkarılmamalı."""
    assert ".kip-basit [data-gelismis]" in STIL.read_text(encoding="utf-8")
    betik = BETIK.read_text(encoding="utf-8")
    for tehlikeli in ("remove()", "removeChild", "innerHTML"):
        assert tehlikeli not in betik, f"betik DOM'u değiştiriyor: {tehlikeli}"


def test_sinif_html_uzerine_ve_icerikten_once_yaziliyor(sablon):
    """Sonra yazılsaydı gelişmiş araçlar bir an görünüp kaybolurdu."""
    assert "document.documentElement.classList.add" in sablon
    # Satır içi betik, gizlenecek ilk bölümden ÖNCE gelmeli.
    assert sablon.index("dalsan-cizim-kipi") < sablon.index('id="arkaplan-secimi"')


def test_localstorage_okunamazsa_sayfa_yine_calisir(sablon):
    """Gizli sekmede / site verisi kapalıyken localStorage erişimi HATA fırlatır.

    Yakalanmazsa satır içi betik çöker, sınıf hiç yazılmaz ve sayfa kipsiz
    (yani her şey açık) kalırdı — üstelik sessizce.
    """
    assert "catch (e)" in sablon
    betik = BETIK.read_text(encoding="utf-8")
    assert betik.count("catch (e)") >= 2, "hem okuma hem yazma korunmalı"


def test_tercih_sunucuda_saklanmiyor(istemci):
    """Bu bir kayıt değil, o kişinin ekran tercihi.

    Sunucuya yazılsaydı bir kullanıcının tercihi herkesin ekranını değiştirirdi.
    """
    kamera_id = _kamera_ekle(istemci)
    # Böyle bir uç HİÇ yok (404); olsaydı tercih sunucuya yazılıyor demekti.
    yanit = istemci.post(f"/kameralar/{kamera_id}/kip", follow_redirects=False)
    assert yanit.status_code == 404
