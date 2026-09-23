"""Saf geometri yardımcıları (yalnızca stdlib)."""

from __future__ import annotations


def nokta_poligonda(nokta: tuple[float, float], poligon: list[tuple[float, float]]) -> bool:
    """Işın yöntemi (ray casting) ile nokta-poligon testi.

    Nokta ve poligon AYNI koordinat uzayında olmalıdır (bu projede: normalize 0-1).
    """
    x, y = nokta
    icinde = False
    n = len(poligon)
    for i in range(n):
        x1, y1 = poligon[i]
        x2, y2 = poligon[(i + 1) % n]
        if (y1 > y) != (y2 > y):
            kesisim_x = (x2 - x1) * (y - y1) / (y2 - y1) + x1
            if x < kesisim_x:
                icinde = not icinde
    return icinde


def oklid_mesafe(a: tuple[float, float], b: tuple[float, float]) -> float:
    return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5


Kutu = tuple[float, float, float, float]  # piksel (x1, y1, x2, y2)


def kutu_alani(kutu: Kutu) -> float:
    return max(0.0, kutu[2] - kutu[0]) * max(0.0, kutu[3] - kutu[1])


def kutu_kesisimi(a: Kutu, b: Kutu) -> float:
    """İki kutunun kesişim ALANI (piksel²); kesişmiyorsa 0."""
    genislik = min(a[2], b[2]) - max(a[0], b[0])
    yukseklik = min(a[3], b[3]) - max(a[1], b[1])
    return max(0.0, genislik) * max(0.0, yukseklik)


def kutu_iou(a: Kutu, b: Kutu) -> float:
    """Kesişim / birleşim (0–1)."""
    kesisim = kutu_kesisimi(a, b)
    birlesim = kutu_alani(a) + kutu_alani(b) - kesisim
    return kesisim / birlesim if birlesim > 0 else 0.0
