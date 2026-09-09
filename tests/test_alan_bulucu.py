"""Alan bulucu — zemindeki boyadan bölge önerisi (app/analiz/alan_bulucu.py).

Kamera GEREKMEZ: sahneler burada üretilir. Sınanan söz şudur — sistem
fabrika zemininde boyayla işaretli alanı bulabilmeli, boya yoksa da
UYDURMAMALI. Yanlış öneri kullanıcının kabul etmediği bir çizimdir, ama
sürekli yanlış öneren bir düğmeye kimse ikinci kez basmaz.
"""

from __future__ import annotations

import cv2
import numpy as np
import pytest

from app.analiz.alan_bulucu import AlanOnerisi, alanlari_bul, maske_onizlemesi

SARI = (0, 215, 245)  # BGR — sahadaki yol boyası
BEYAZ = (235, 235, 235)


def zemin(genislik: int = 960, yukseklik: int = 540) -> np.ndarray:
    """Dokulu gri beton: düz renk, gerçek bir kamera karesine benzemez."""
    kare = np.full((yukseklik, genislik, 3), 120, np.uint8)
    gurultu = np.random.default_rng(0).integers(0, 20, (yukseklik, genislik, 3), dtype=np.uint8)
    return cv2.add(kare, gurultu)


def yaya_yolu_zemini() -> np.ndarray:
    """İki paralel KESİKLİ sarı çizgi — sahadaki en yaygın yaya yolu işareti."""
    kare = zemin()
    for x in range(80, 880, 60):
        cv2.rectangle(kare, (x, 200), (x + 38, 212), SARI, -1)
        cv2.rectangle(kare, (x, 330), (x + 38, 342), SARI, -1)
    return kare


def yukleme_alani_zemini() -> np.ndarray:
    """Beyaz çerçeveyle işaretli dikdörtgen alan."""
    kare = zemin()
    cv2.rectangle(kare, (300, 120), (700, 430), BEYAZ, 14)
    return kare


def test_paralel_sari_cizgiler_yaya_yolu_onerir():
    oneriler = alanlari_bul(yaya_yolu_zemini())
    assert oneriler, "İki paralel sarı çizgiyle işaretli yol bulunamadı"
    en_iyi = oneriler[0]
    assert en_iyi.tip == "pedestrian_path"
    assert en_iyi.tip_adi == "Yaya yolu"


def test_onerilen_alan_cizgilerin_arasini_kapsar():
    """Öneri, iki çizginin ARASINI da içermeli — yol orasıdır, çizgiler değil."""
    en_iyi = alanlari_bul(yaya_yolu_zemini())[0]
    ys = [y for _, y in en_iyi.poligon]
    # Çizgiler 200-342 piksel (540 yükseklikte) → 0,37-0,63 bandı
    assert min(ys) < 0.42, f"Üst çizgi kapsanmamış: {en_iyi.poligon}"
    assert max(ys) > 0.58, f"Alt çizgi kapsanmamış: {en_iyi.poligon}"


def test_beyaz_cerceve_yukleme_alani_onerir():
    oneriler = alanlari_bul(yukleme_alani_zemini())
    assert oneriler
    assert oneriler[0].tip == "loading_area"


def test_bos_zeminde_oneri_uretilmez():
    """Boyasız betonda öneri uydurulmaz — bulunamadı, bulunamadıdır."""
    assert alanlari_bul(zemin()) == []


def test_poligon_normalize_ve_gecerli():
    """Kaydetme doğrulaması (kameralar.py) 0-1 aralığı ve >=3 nokta şart koşar."""
    for oneri in alanlari_bul(yaya_yolu_zemini()) + alanlari_bul(yukleme_alani_zemini()):
        assert len(oneri.poligon) >= 3
        assert all(0.0 <= x <= 1.0 and 0.0 <= y <= 1.0 for x, y in oneri.poligon)


def test_kose_sayisi_elle_duzeltilebilir_kalir():
    """30 köşeli bir alanı kullanıcı düzeltemez; üst sınır korunmalı."""
    for oneri in alanlari_bul(yaya_yolu_zemini()):
        assert len(oneri.poligon) <= 12


def test_bos_kare_cokmez():
    assert alanlari_bul(np.zeros((0, 0, 3), np.uint8)) == []
    assert alanlari_bul(None) == []


def test_buyuk_kare_kucultulerek_islenir():
    """4K karede de çalışmalı ve normalize koordinat aynı yeri göstermeli."""
    kare = cv2.resize(yaya_yolu_zemini(), (3840, 2160), interpolation=cv2.INTER_NEAREST)
    oneriler = alanlari_bul(kare)
    assert oneriler
    ys = [y for _, y in oneriler[0].poligon]
    assert min(ys) < 0.42 and max(ys) > 0.58


def test_maske_onizlemesi_ayni_boyutta_gorsel_verir():
    kare = yaya_yolu_zemini()
    onizleme = maske_onizlemesi(kare)
    assert onizleme is not None
    assert onizleme.shape == kare.shape
    assert maske_onizlemesi(None) is None


def test_alan_yuzdesi_makul():
    en_iyi = alanlari_bul(yukleme_alani_zemini())[0]
    # 400x310 / 960x540 = %23,9 — çerçeve kalınlığıyla birlikte biraz üstü
    assert 15.0 < en_iyi.alan_yuzdesi < 40.0


@pytest.mark.parametrize("guven", [0.0, 0.5, 1.0])
def test_guven_araligi(guven):
    """Güven 0-1 arası olmalı: arayüz bunu yüzde olarak gösterir."""
    oneri = AlanOnerisi(
        poligon=[(0.0, 0.0), (1.0, 0.0), (1.0, 1.0)],
        tip="restricted",
        tip_adi="Yasak bölge",
        guven=guven,
        aciklama="",
    )
    assert 0.0 <= oneri.guven <= 1.0
    assert oneri.alan_yuzdesi == 50.0  # üçgen, karenin yarısı


def test_oneriler_guvene_gore_sirali():
    kare = yaya_yolu_zemini()
    cv2.rectangle(kare, (60, 400), (300, 520), BEYAZ, 10)
    oneriler = alanlari_bul(kare)
    guvenler = [o.guven for o in oneriler]
    assert guvenler == sorted(guvenler, reverse=True)


def test_en_cok_sayisi_asilmaz():
    kare = zemin()
    for i in range(6):
        cv2.rectangle(kare, (20 + i * 150, 40), (140 + i * 150, 200), BEYAZ, 10)
    assert len(alanlari_bul(kare, en_cok=3)) <= 3
