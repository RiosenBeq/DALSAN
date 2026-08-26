"""Kural testleri için sahte veri üreticileri (kamera YOK, model YOK).

Kare 1000x1000 piksel kabul edilir → normalize koordinat = piksel / 1000.
"""

from __future__ import annotations

from app.rules.tipler import Bolge, Kalibrasyon, KkdGozlem, Kural, Tespit

KARE = (1000.0, 1000.0)

# Karenin ortasında bir bölge: (0.25,0.25)-(0.75,0.75)
ORTA_BOLGE = [(0.25, 0.25), (0.75, 0.25), (0.75, 0.75), (0.25, 0.75)]

# Normalize görüntü → metre: 0-1 aralığı 10 metreye eşlenir.
# (0.5, 0.5) → (5 m, 5 m). Testlerde mesafe hesabını akılda tutmak kolay olsun.
KALIBRASYON_10M = Kalibrasyon(homografi=[[10.0, 0, 0], [0, 10.0, 0], [0, 0, 1.0]])


def bolge(bolge_id: int = 1, tip: str = "restricted", poligon=None) -> Bolge:
    return Bolge(id=bolge_id, tip=tip, poligon=poligon or list(ORTA_BOLGE))


def kural(
    tip: str,
    kural_id: int = 1,
    bolge_id: int | None = 1,
    hedefler: list[str] | None = None,
    params: dict | None = None,
    cooldown_s: float = 60.0,
) -> Kural:
    return Kural(
        id=kural_id,
        kamera_id=1,
        tip=tip,
        bolge_id=bolge_id,
        hedef_siniflar=hedefler or ["person"],
        params=params or {},
        cooldown_s=cooldown_s,
    )


def tespit(
    sinif: str = "person",
    ayak: tuple[float, float] = (0.5, 0.5),  # normalize ayak noktası
    takip_id: int = 1,
    boy_px: float = 200.0,
    kkd: KkdGozlem | None = None,
) -> Tespit:
    """Ayak noktası verilen normalize konumda, boyu boy_px olan tespit üretir."""
    x = ayak[0] * KARE[0]
    y = ayak[1] * KARE[1]
    return Tespit(
        sinif=sinif,
        kutu=(x - 40, y - boy_px, x + 40, y),
        takip_id=takip_id,
        guven=0.9,
        kkd_gozlemi=kkd,
    )
