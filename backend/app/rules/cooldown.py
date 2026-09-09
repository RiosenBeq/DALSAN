"""Cooldown — tekrar uyarı bastırma, tüm kural tiplerinin ortak filtresi.

Saf: zamanı kendisi ölçmez, çağıran verir. Böylece testte zaman ileri
sarılabilir (docs/03 §5).
"""

from __future__ import annotations

Anahtar = tuple  # (kural_id, kamera_id, takip_id) veya (kural_id, kamera_id, id1, id2)


class Cooldown:
    def __init__(self) -> None:
        self._son: dict[Anahtar, float] = {}

    def izinli_mi(self, anahtar: Anahtar, zaman_s: float, sure_s: float) -> bool:
        """İzin varsa zamanı kaydedip True döner; cooldown içindeyse False."""
        son = self._son.get(anahtar)
        if son is not None and (zaman_s - son) < sure_s:
            return False
        self._son[anahtar] = zaman_s
        return True

    def temizle(self, esik_zaman_s: float) -> None:
        """Uzun süredir görülmeyen anahtarları at (bellek büyümesin)."""
        self._son = {a: z for a, z in self._son.items() if z >= esik_zaman_s}

    def kural_sifirla(self, kural_id: int) -> None:
        """Bir kuralın tüm cooldown geçmişini siler (anahtarın ilk öğesi kural id).

        Kural tanımı değişince veya silinen kuralın id'si yeni bir kurala
        verilince eski bastırma geçmişi taşınmamalı.
        """
        self._son = {a: z for a, z in self._son.items() if not a or a[0] != kural_id}
