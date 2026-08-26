"""safe_distance testleri: kalibrasyon şartı, hareket koşulu, cooldown."""

from __future__ import annotations

from yardimci import KALIBRASYON_10M, KARE, bolge, kural, tespit

from app.rules.motor import KuralMotoru


def _motor(params: dict | None = None, cooldown_s: float = 60.0):
    motor = KuralMotoru(kamera_id=1)
    varsayilan = {"distance_m": 3.0, "min_frames": 3, "min_speed_mps": 0.3}
    motor.kurallari_yukle(
        [
            kural(
                "safe_distance",
                bolge_id=None,
                hedefler=["person", "truck"],
                params={**varsayilan, **(params or {})},
                cooldown_s=cooldown_s,
            )
        ]
    )
    return motor


def _hareketli_senaryo(motor, adim_sayisi: int, arac_hizli: bool = True):
    """İnsan sabit (0.5, 0.5); araç her 0.2 sn'de yaklaşır (hızlı ise).

    Adım başına 0.01 normalize birim = 0.1 m → 0.5 m/sn (eşik 0.3'ün üstü).
    """
    ihlaller = []
    for i in range(adim_sayisi):
        zaman = i * 0.2
        arac_x = 0.56 - (0.01 * i if arac_hizli else 0.0)
        tespitler = [
            tespit(ayak=(0.5, 0.5), takip_id=1),
            tespit(sinif="truck", ayak=(arac_x, 0.5), takip_id=2),
        ]
        ihlaller.extend(motor.degerlendir(zaman, KARE, tespitler, [bolge()], KALIBRASYON_10M))
    return ihlaller


def test_kalibrasyonsuz_kamerada_kural_pasif():
    # Yaklaşık piksel mesafesi ÜRETİLMEZ — kural açıkça çalışmaz (docs/03 §2)
    motor = _motor()
    for i in range(10):
        tespitler = [
            tespit(ayak=(0.5, 0.5), takip_id=1),
            tespit(sinif="truck", ayak=(0.51, 0.5), takip_id=2),  # 0.1 m yakın!
        ]
        assert motor.degerlendir(i * 0.2, KARE, tespitler, [bolge()], None) == []


def test_yakin_ve_hareketli_arac_ihlal_uretir():
    ihlaller = _hareketli_senaryo(_motor(), adim_sayisi=8)
    assert len(ihlaller) == 1
    ihlal = ihlaller[0]
    assert sorted(ihlal.takip_idler) == [1, 2]
    assert ihlal.olculen is not None and ihlal.olculen < 3.0
    assert ihlal.detaylar["arac_sinifi"] == "truck"


def test_duran_arac_ihlal_uretmez():
    # Park halindeki tırın yanındaki şoför gerçek risk değildir (docs/03 §2)
    ihlaller = _hareketli_senaryo(_motor(), adim_sayisi=10, arac_hizli=False)
    assert ihlaller == []


def test_hareket_kosulu_kapatilirsa_duran_arac_da_ihlal():
    motor = _motor({"require_moving_vehicle": False})
    ihlaller = _hareketli_senaryo(motor, adim_sayisi=6, arac_hizli=False)
    assert len(ihlaller) == 1


def test_uzak_arac_ihlal_uretmez():
    motor = _motor()
    for i in range(10):
        tespitler = [
            tespit(ayak=(0.2, 0.5), takip_id=1),
            tespit(sinif="truck", ayak=(0.9, 0.5), takip_id=2),  # 7 m uzakta
        ]
        assert motor.degerlendir(i * 0.2, KARE, tespitler, [bolge()], KALIBRASYON_10M) == []


def test_min_frames_tek_karelik_yakinligi_eler():
    # Araç bir anlık yaklaşıp uzaklaşırsa (tek kare) uyarı ÜRETİLMEZ
    motor = _motor({"min_frames": 3, "require_moving_vehicle": False})
    konumlar = [0.56, 0.56, 0.9, 0.9, 0.56, 0.9]  # ardışık 3 yakınlık hiç yok
    for i, arac_x in enumerate(konumlar):
        tespitler = [
            tespit(ayak=(0.5, 0.5), takip_id=1),
            tespit(sinif="truck", ayak=(arac_x, 0.5), takip_id=2),
        ]
        assert motor.degerlendir(i * 0.2, KARE, tespitler, [bolge()], KALIBRASYON_10M) == []


def test_cift_bazli_cooldown():
    motor = _motor(cooldown_s=60.0)
    assert len(_hareketli_senaryo(motor, adim_sayisi=8)) == 1
    # Aynı çift yakın kalmaya devam ediyor — cooldown içinde yeni olay yok
    assert _hareketli_senaryo(motor, adim_sayisi=8) == []
