"""ppe_violation testleri — motorun en kritik kuralı (docs/03 §3, docs/04).

KANITIN YOKLUĞU İHLALİN VARLIĞI DEĞİLDİR:
`belirsiz` hiçbir zaman olay üretmez; bu dosyadaki ilk test bunun bekçisidir.
"""

from __future__ import annotations

from yardimci import KARE, bolge, kural, tespit

from app.rules.motor import KuralMotoru
from app.rules.tipler import BELIRSIZ, VAR, YOK, KkdGozlem

PARAMS = {
    "required_ppe": ["helmet"],
    "min_person_height_px": 120,
    "min_confidence": 0.7,
    "window_size": 15,
    "min_valid_observations": 8,
    "violation_ratio": 0.75,
    "min_dwell_s": 3.0,
    "require_full_bbox": True,
}


def _motor(params: dict | None = None, cooldown_s: float = 180.0):
    motor = KuralMotoru(kamera_id=1)
    motor.kurallari_yukle(
        [
            kural(
                "ppe_violation",
                params={**PARAMS, **(params or {})},
                cooldown_s=cooldown_s,
            )
        ]
    )
    return motor


def _gozlem(baret: str, guven: float = 0.9) -> KkdGozlem:
    return KkdGozlem(
        baret=baret, yelek=VAR, baret_guven=guven, yelek_guven=0.9, model_surumu="kkd-test-v1"
    )


def _kisi(baret: str | None, boy_px: float = 200.0, guven: float = 0.9, takip_id: int = 1):
    """KKD bölgesinin ortasında bir kişi. baret=None → gözlem üretilmedi (model yok)."""
    return tespit(
        ayak=(0.5, 0.5),
        takip_id=takip_id,
        boy_px=boy_px,
        kkd=_gozlem(baret, guven) if baret is not None else None,
    )


def _calistir(motor, zaman_s, tespitler):
    return motor.degerlendir(zaman_s, KARE, tespitler, [bolge(tip="ppe_required")], None)


def _seri(motor, adet: int, baret: str | None, baslangic: float = 0.0, **kisi_args):
    """adet kez 0.5 sn arayla değerlendirme; toplam ihlalleri döndürür."""
    ihlaller = []
    for i in range(adet):
        ihlaller.extend(_calistir(motor, baslangic + i * 0.5, [_kisi(baret, **kisi_args)]))
    return ihlaller


def test_belirsiz_asla_olay_uretmez():
    """docs/04 §1 — bu testin kırmızıya dönmesi tasarım ihlalidir."""
    # 1) Model hiç gözlem üretmiyor (None)
    assert _seri(_motor(), 30, None) == []
    # 2) Model açıkça 'belirsiz' diyor
    assert _seri(_motor(), 30, BELIRSIZ) == []
    # 3) Gözlem 'yok' diyor ama güven eşiğin ALTINDA → belirsiz sayılır
    assert _seri(_motor(), 30, YOK, guven=0.5) == []


def test_tutarli_yok_gozlemi_ihlal_uretir():
    motor = _motor()
    ihlaller = _seri(motor, 12, YOK)  # 6 sn, 12 geçerli 'yok' gözlemi
    assert len(ihlaller) == 1
    detay = ihlaller[0].detaylar["ppe"]
    assert detay["helmet"]["decision"] == "no"
    assert detay["helmet"]["valid_obs"] >= 8
    assert detay["model_version"] == "kkd-test-v1"
    assert ihlaller[0].detaylar["eksik_kkd"] == ["helmet"]


def test_bareti_olan_ihlal_uretmez():
    assert _seri(_motor(), 30, VAR) == []


def test_yetersiz_gecerli_gozlem_olay_uretmez():
    # 15'lik pencerede yalnızca 5 geçerli gözlem (< 8) — kanıt yetersiz
    motor = _motor()
    ihlaller = []
    for i in range(30):
        baret = YOK if i % 6 == 0 else BELIRSIZ  # seyrek geçerli gözlem
        ihlaller.extend(_calistir(motor, i * 0.5, [_kisi(baret)]))
    assert ihlaller == []


def test_oran_altinda_karisik_gozlem_olay_uretmez():
    # Geçerli gözlemlerin yarısı 'yok' (< %75) → karar VAR/karışık, olay yok
    motor = _motor()
    ihlaller = []
    for i in range(30):
        ihlaller.extend(_calistir(motor, i * 0.5, [_kisi(YOK if i % 2 else VAR)]))
    assert ihlaller == []


def test_kucuk_kisi_degerlendirilmez():
    # 120 px altındaki kişi için gözlem BELİRSİZE zorlanır (docs/04 §3)
    assert _seri(_motor(), 30, YOK, boy_px=80) == []


def test_kesik_kutu_degerlendirilmez():
    # Kare kenarına dayanan kutu (require_full_bbox) → belirsiz
    motor = _motor()
    ihlaller = []
    for i in range(30):
        kisi = tespit(ayak=(0.02, 0.5), takip_id=1, boy_px=200, kkd=_gozlem(YOK))
        ihlaller.extend(_calistir(motor, i * 0.5, [kisi]))
    assert ihlaller == []


def test_dwell_dolmadan_olay_uretilmez():
    # 3 sn dolmadan, gözlemler yeterli olsa bile olay yok
    motor = _motor()
    assert _seri(motor, 5, YOK) == []  # 2 sn


def test_cooldown():
    motor = _motor(cooldown_s=180.0)
    assert len(_seri(motor, 12, YOK)) == 1
    # kişi baretsiz kalmaya devam ediyor — 3 dk içinde yeni olay yok
    assert _seri(motor, 20, YOK, baslangic=6.0) == []
    # cooldown dolunca tekrar
    assert len(_seri(motor, 4, YOK, baslangic=200.0)) == 1


def test_bolge_disinda_kkd_degerlendirilmez():
    motor = _motor()
    ihlaller = []
    for i in range(30):
        kisi = tespit(ayak=(0.05, 0.9), takip_id=1, boy_px=200, kkd=_gozlem(YOK))
        ihlaller.extend(_calistir(motor, i * 0.5, [kisi]))
    assert ihlaller == []
