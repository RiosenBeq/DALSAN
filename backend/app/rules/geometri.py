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
