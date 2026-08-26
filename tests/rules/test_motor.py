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


def test_hedef_sinif_degisikligi_hemen_uygulanir():
    """Kullanıcı hedef sınıfı değiştirince (örn. insan → forklift) kural
    RESTART BEKLEMEDEN yeni sınıfla çalışmalı — güvenlik kuralının kayıtlı
    yapılandırmadan farklı çalışması kabul edilemez."""
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [kural("zone_intrusion", hedefler=["person"], params={"min_dwell_s": 1.0})]
    )
    insan = [tespit(ayak=(0.5, 0.5), takip_id=1)]
    forklift = [tespit(sinif="forklift", ayak=(0.5, 0.5), takip_id=2)]
    motor.degerlendir(0.0, KARE, insan, [bolge()], None)
    assert len(motor.degerlendir(1.5, KARE, insan, [bolge()], None)) == 1

    # Yalnızca hedef sınıf değişti — başka hiçbir alan değişmedi
    motor.kurallari_yukle(
        [kural("zone_intrusion", hedefler=["forklift"], params={"min_dwell_s": 1.0})]
    )
    motor.degerlendir(2.0, KARE, forklift, [bolge()], None)
    assert len(motor.degerlendir(3.5, KARE, forklift, [bolge()], None)) == 1
    # İnsan artık hedef değil
    motor.degerlendir(4.0, KARE, insan, [bolge()], None)
    assert motor.degerlendir(6.0, KARE, insan, [bolge()], None) == []


def test_uzun_cooldown_kirpilmiyor():
    # 2 saatlik cooldown, 1 saatlik bellek temizliğine kurban gitmemeli
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([kural("zone_intrusion", params={"min_dwell_s": 1.0}, cooldown_s=7200.0)])
    icerde = [tespit(ayak=(0.5, 0.5))]
    motor.degerlendir(0.0, KARE, icerde, [bolge()], None)
    assert len(motor.degerlendir(1.5, KARE, icerde, [bolge()], None)) == 1
    # 1 saat sonra hâlâ bastırılıyor olmalı (eski hata: burada tekrar olay üretirdi)
    for zaman in (3600.0, 5000.0, 7000.0):
        assert motor.degerlendir(zaman, KARE, icerde, [bolge()], None) == []
    # 2 saat dolunca serbest
    assert len(motor.degerlendir(7202.0, KARE, icerde, [bolge()], None)) == 1


def test_kural_degisince_cooldown_mirasi_kalmaz():
    """Silinen kuralın id'sini alan YENİ kural, eskisinin bastırma geçmişini
    devralmamalı — yoksa yeni kuralın ilk ihlali sessizce yutulur."""
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([kural("zone_intrusion", params={"min_dwell_s": 1.0})])
    icerde = [tespit(ayak=(0.5, 0.5))]
    motor.degerlendir(0.0, KARE, icerde, [bolge()], None)
    assert len(motor.degerlendir(1.5, KARE, icerde, [bolge()], None)) == 1  # cooldown doldu

    # Aynı id ile TANIMI FARKLI bir kural geldi (silinip yeniden oluşturuldu)
    motor.kurallari_yukle(
        [kural("zone_intrusion", params={"min_dwell_s": 1.0, "mode": "inside"}, cooldown_s=90.0)]
    )
    motor.degerlendir(2.0, KARE, icerde, [bolge()], None)
    assert len(motor.degerlendir(3.5, KARE, icerde, [bolge()], None)) == 1


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
