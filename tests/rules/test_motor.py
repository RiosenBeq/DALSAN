"""Motor testleri: hız tahmini, restart'sız konfigürasyon, geometri."""

from __future__ import annotations

from yardimci import KALIBRASYON_10M, KARE, ORTA_BOLGE, bolge, kural, tespit

from app.rules.geometri import nokta_poligonda
from app.rules.motor import KuralMotoru


def test_hiz_tahmini_kalibrasyonlu_kamerada():
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([])
    # 0.2 sn'de 0.02 normalize birim = 0.2 m → 1 m/sn
    t1 = tespit(sinif="truck", ayak=(0.50, 0.5), takip_id=7)
    motor.degerlendir(0.0, KARE, [t1], [], KALIBRASYON_10M)
    t2 = tespit(sinif="truck", ayak=(0.52, 0.5), takip_id=7)
    motor.degerlendir(0.2, KARE, [t2], [], KALIBRASYON_10M)
    assert t2.hiz_mps is not None
    assert abs(t2.hiz_mps - 1.0) < 0.05


def test_hiz_kalibrasyonsuz_hesaplanmaz():
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([])
    t1 = tespit(ayak=(0.5, 0.5))
    motor.degerlendir(0.0, KARE, [t1], [], None)
    t2 = tespit(ayak=(0.6, 0.5))
    motor.degerlendir(0.2, KARE, [t2], [], None)
    assert t2.hiz_mps is None  # piksel hızı yanıltıcıdır, üretilmez


def test_ayni_konfigurasyonda_durum_korunur():
    """Restart'sız config yayılımı (docs/02 §5): kurallar değişmediyse
    kalış süreleri/pencereler sıfırlanmamalı."""
    motor = KuralMotoru(kamera_id=1)
    kurallar = [kural("zone_intrusion", params={"mode": "inside", "min_dwell_s": 2.0})]
    motor.kurallari_yukle(kurallar)
    icerde = [tespit(ayak=(0.5, 0.5))]
    motor.degerlendir(0.0, KARE, icerde, [bolge()], None)
    # Süpervizör her konfig kontrolünde yeniden yükler — durum korunmalı
    motor.kurallari_yukle(kurallar)
    ihlaller = motor.degerlendir(2.5, KARE, icerde, [bolge()], None)
    assert len(ihlaller) == 1  # kalış süresi baştan başlamadı


def test_konfigurasyon_degisince_yeni_parametre_gecerli():
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([kural("zone_intrusion", params={"min_dwell_s": 2.0})])
    icerde = [tespit(ayak=(0.5, 0.5))]
    motor.degerlendir(0.0, KARE, icerde, [bolge()], None)
    # Parametre değişti: artık 30 sn kalış gerekiyor
    motor.kurallari_yukle([kural("zone_intrusion", params={"min_dwell_s": 30.0})])
    assert motor.degerlendir(2.5, KARE, icerde, [bolge()], None) == []


def test_nokta_poligonda():
    assert nokta_poligonda((0.5, 0.5), ORTA_BOLGE)
    assert not nokta_poligonda((0.1, 0.1), ORTA_BOLGE)
    assert not nokta_poligonda((0.76, 0.5), ORTA_BOLGE)
    # Üçgen poligon
    ucgen = [(0.0, 0.0), (1.0, 0.0), (0.5, 1.0)]
    assert nokta_poligonda((0.5, 0.5), ucgen)
    assert not nokta_poligonda((0.05, 0.9), ucgen)
