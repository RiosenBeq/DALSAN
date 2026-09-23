"""Geçit istisnası, mesafe histerezisi ve R21 (docs/17 §6.3, §6.4; Faz 2c-4).

- Yaya-araç geçidinde (crossing) bölge ihlali yok: araç yolunu geçitten geçen
  yaya, geçitten geçen forklift uyarı üretmez (`gecit_haric`, varsayılan açık).
- Açılmış mesafe olayı, mesafe `distance_m + histerezis_m`'yi aşınca biter:
  eşiğin hemen üstünde gidip gelen çift tek olay kalır.
- R21: bölgeye bağlı mesafe kuralı, bölgesi kapalıysa ya da yoksa çalışmaz.
"""

from __future__ import annotations

from yardimci import KALIBRASYON_10M, KARE, bolge, kural, tespit

from app.rules.motor import KuralMotoru
from app.rules.olay_durumu import ACILDI, KAPANDI
from app.rules.tipler import Bolge

# Araç yolu karenin ortası; geçit onun içinde dikey bir şerit
GECIT = [(0.45, 0.25), (0.55, 0.25), (0.55, 0.75), (0.45, 0.75)]
YOLDA = (0.35, 0.5)
GECITTE = (0.5, 0.5)


def _gecit(aktif: bool = True, bolge_id: int = 9) -> Bolge:
    return Bolge(id=bolge_id, tip="crossing", poligon=list(GECIT), aktif=aktif)


def _arac_yolu_kurali(**params):
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [kural("zone_intrusion", params={"mode": "inside", "min_dwell_s": 1.0, **params})]
    )
    return motor


def _ihlal_sayisi(motor, ayak, bolgeler, adim=6):
    return sum(
        len(motor.degerlendir(t * 0.5, KARE, [tespit(ayak=ayak)], bolgeler, None))
        for t in range(adim)
    )


# ------------------------------------------------------------------ geçit


def test_gecitteki_yaya_ihlal_uretmez():
    bolgeler = [bolge(tip="vehicle_area"), _gecit()]
    assert _ihlal_sayisi(_arac_yolu_kurali(), GECITTE, bolgeler) == 0
    # Aynı yolda geçidin dışında: ihlal
    assert _ihlal_sayisi(_arac_yolu_kurali(), YOLDA, bolgeler) == 1


def test_gecit_haric_kapatilirsa_gecitte_de_ihlal():
    bolgeler = [bolge(tip="vehicle_area"), _gecit()]
    assert _ihlal_sayisi(_arac_yolu_kurali(gecit_haric=False), GECITTE, bolgeler) == 1


def test_kapali_gecit_istisna_yapmaz():
    bolgeler = [bolge(tip="vehicle_area"), _gecit(aktif=False)]
    assert _ihlal_sayisi(_arac_yolu_kurali(), GECITTE, bolgeler) == 1


def test_yaya_yolu_disinda_ama_gecitte_olan_yaya_ihlal_uretmez():
    """ "Yaya yolunu kullan" kuralı (outside): yolu geçitten geçen kişi ihlal değil."""
    yaya_yolu = Bolge(id=1, tip="pedestrian_path", poligon=[(0, 0), (0.2, 0), (0.2, 1), (0, 1)])
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([kural("zone_intrusion", params={"mode": "outside", "min_dwell_s": 1.0})])
    assert _ihlal_sayisi(motor, GECITTE, [yaya_yolu, _gecit()]) == 0
    assert _ihlal_sayisi(motor, (0.8, 0.9), [yaya_yolu, _gecit()]) == 1


def test_gecidin_kendisini_izleyen_kural_istisnaya_takilmaz():
    """Kural doğrudan geçit bölgesine kurulmuşsa istisna o kuralı susturmaz."""
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([kural("zone_intrusion", bolge_id=9, params={"min_dwell_s": 1.0})])
    assert _ihlal_sayisi(motor, GECITTE, [_gecit(bolge_id=9)]) == 1


def test_gecide_gecen_kisinin_olayi_biter():
    motor = _arac_yolu_kurali()
    bolgeler = [bolge(tip="vehicle_area"), _gecit()]
    gecisler = []
    for t in range(4):  # yolda: olay açılır
        motor.degerlendir(t * 0.5, KARE, [tespit(ayak=YOLDA)], bolgeler, None)
        gecisler += motor.gecisleri_al()
    for t in range(4, 14):  # geçide çıktı
        motor.degerlendir(t * 0.5, KARE, [tespit(ayak=GECITTE)], bolgeler, None)
        gecisler += motor.gecisleri_al()
    assert [(g.asama, g.sebep) for g in gecisler] == [(ACILDI, ""), (KAPANDI, "kosul_bitti")]


# ------------------------------------------------------------------ histerezis


def _mesafe_motoru(**params):
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [
            kural(
                "safe_distance",
                bolge_id=None,
                params={"min_frames": 2, "require_moving_vehicle": False, **params},
            )
        ]
    )
    return motor


def _mesafe_oynat(motor, mesafeler_m, adim_s=0.5):
    """Kişi (0.1, 0.5)'te; forklift x ekseninde verilen mesafede (1 birim = 10 m)."""
    gecisler = []
    for i, mesafe_m in enumerate(mesafeler_m):
        tespitler = [
            tespit(ayak=(0.1, 0.5), takip_id=1),
            tespit(sinif="forklift", ayak=(0.1 + mesafe_m / 10, 0.5), takip_id=2),
        ]
        motor.degerlendir(i * adim_s, KARE, tespitler, [], KALIBRASYON_10M)
        gecisler += [(i * adim_s, g.asama) for g in motor.gecisleri_al()]
    return gecisler


def test_esigin_hemen_ustunde_gidip_gelen_cift_tek_olay():
    """distance_m 3, histerezis 0,5: 3,3 m olay bitirmez; 2,5↔3,3 tek olay."""
    gecisler = _mesafe_oynat(_mesafe_motoru(), [2.5, 2.5] + [3.3, 2.5] * 10)
    assert [a for _, a in gecisler] == [ACILDI]


def test_histerezisi_asan_cift_bitis_s_sonra_kapanir():
    gecisler = _mesafe_oynat(_mesafe_motoru(), [2.5, 2.5] + [3.8] * 10)
    assert gecisler == [(0.5, ACILDI), (3.5, KAPANDI)]  # son yakın an 0,5 + bitis_s 3


def test_histerezis_sifirsa_esigin_ustu_olayi_bitirir():
    gecisler = _mesafe_oynat(_mesafe_motoru(histerezis_m=0.0), [2.5, 2.5] + [3.3] * 10)
    assert [a for _, a in gecisler] == [ACILDI, KAPANDI]


# ------------------------------------------------------------------ R21


def _bolgeli_mesafe(bolgeler):
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [kural("safe_distance", params={"min_frames": 1, "require_moving_vehicle": False})]
    )
    tespitler = [
        tespit(ayak=(0.5, 0.5), takip_id=1),
        tespit(sinif="forklift", ayak=(0.6, 0.5), takip_id=2),
    ]
    return motor.degerlendir(0.0, KARE, tespitler, bolgeler, KALIBRASYON_10M)


def test_bolgesi_kapali_mesafe_kurali_calismaz():
    assert len(_bolgeli_mesafe([bolge(tip="vehicle_area")])) == 1
    kapali = bolge(tip="vehicle_area")
    kapali.aktif = False
    assert _bolgeli_mesafe([kapali]) == []


def test_bolgesi_yuklenemeyen_mesafe_kurali_butun_kareye_yayilmaz():
    """Eskiden bölge bulunamayınca kural bütün karede çalışıyordu."""
    assert _bolgeli_mesafe([]) == []
