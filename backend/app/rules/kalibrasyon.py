"""4 nokta zemin homografisi — saf numpy (OpenCV YOK, CLAUDE.md §6).

Normalize görüntü koordinatı (0-1) → zemin düzlemi (metre) dönüşümü.
Kalibre edilmemiş kamerada mesafe kuralı ÇALIŞMAZ; yaklaşık sonuç üretilmez
(docs/03 §2). Bu modül yalnızca matematiği içerir.
"""

from __future__ import annotations

import numpy as np

from app.hatalar import DalsanHata


class KalibrasyonHatasi(DalsanHata):
    http_kodu = 400


def homografi_hesapla(
    goruntu_noktalari: list[tuple[float, float]],
    dunya_noktalari: list[tuple[float, float]],
) -> list[list[float]]:
    """4 eşleşen noktadan 3x3 homografi (DLT yöntemi).

    goruntu_noktalari: normalize (0-1) görüntü koordinatları
    dunya_noktalari: zemindeki karşılıkları, metre cinsinden
    """
    if len(goruntu_noktalari) != 4 or len(dunya_noktalari) != 4:
        raise KalibrasyonHatasi("Kalibrasyon için tam olarak 4 nokta çifti gerekir.")

    a_satirlari, b = [], []
    for (x, y), (dx, dy) in zip(goruntu_noktalari, dunya_noktalari, strict=True):
        a_satirlari.append([x, y, 1, 0, 0, 0, -dx * x, -dx * y])
        a_satirlari.append([0, 0, 0, x, y, 1, -dy * x, -dy * y])
        b.extend([dx, dy])
    try:
        h = np.linalg.solve(np.array(a_satirlari, dtype=float), np.array(b, dtype=float))
    except np.linalg.LinAlgError as hata:
        raise KalibrasyonHatasi(
            "Kalibrasyon hesaplanamadı: seçilen 4 nokta aynı doğru üzerinde olabilir. "
            "Zeminde bir dikdörtgen oluşturacak 4 ayrı nokta seçin."
        ) from hata
    matris = np.append(h, 1.0).reshape(3, 3)
    return matris.tolist()


def dunyaya_cevir(homografi: list[list[float]], nokta: tuple[float, float]) -> tuple[float, float]:
    """Normalize görüntü noktasını zemin düzlemine (metre) yansıtır."""
    matris = np.array(homografi, dtype=float)
    vektor = matris @ np.array([nokta[0], nokta[1], 1.0])
    if abs(vektor[2]) < 1e-9:
        raise KalibrasyonHatasi("Kalibrasyon bu noktayı zemine yansıtamıyor (ufuk çizgisi).")
    return float(vektor[0] / vektor[2]), float(vektor[1] / vektor[2])
