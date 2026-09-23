"""KKD muaf alan (ppe_exempt) zorunlu alandan oyulur (docs/17 §5.5; Faz 2e-1).

Kabin, ofis köşesi gibi muaf alandaki kişi KKD kuralınca değerlendirilmez:
zorunlu alanın dışında sayılır. Kapalı muaf alan oyma yapmaz.
"""

from __future__ import annotations

from yardimci import KARE, bolge, kural, tespit

from app.rules.motor import KuralMotoru
from app.rules.tipler import VAR, YOK, Bolge, KkdGozlem

# Zorunlu alanın (0.25–0.75) ortasında küçük bir muaf kare
MUAF = [(0.4, 0.4), (0.6, 0.4), (0.6, 0.6), (0.4, 0.6)]


def _baretsiz() -> KkdGozlem:
    return KkdGozlem(
        baret=YOK, yelek=VAR, baret_guven=0.9, yelek_guven=0.9, model_surumu="kkd-test-v1"
    )


def _ihlaller(bolgeler, ayak) -> list:
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle([kural("ppe_violation", params={"required_ppe": ["helmet"]})])
    ihlaller = []
    for i in range(20):  # 10 sn: pencere dolar, kalış aşılır
        ihlaller += motor.degerlendir(
            i * 0.5, KARE, [tespit(ayak=ayak, kkd=_baretsiz())], bolgeler, None
        )
    return ihlaller


def test_muaf_alandaki_kisi_kkd_ihlali_uretmez():
    bolgeler = [bolge(tip="ppe_required"), Bolge(id=2, tip="ppe_exempt", poligon=list(MUAF))]
    assert _ihlaller(bolgeler, (0.5, 0.5)) == []
    # Aynı zorunlu alanda, muafın dışında: ihlal
    assert len(_ihlaller(bolgeler, (0.3, 0.3))) == 1


def test_kapali_muaf_alan_oymaz():
    muaf = Bolge(id=2, tip="ppe_exempt", poligon=list(MUAF), aktif=False)
    assert len(_ihlaller([bolge(tip="ppe_required"), muaf], (0.5, 0.5))) == 1
