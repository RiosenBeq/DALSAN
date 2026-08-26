"""KKD (baret/yelek) sınıflandırıcısı — iki aşamalı yaklaşımın 2. aşaması.

İnsan kutusu kırpılır (üstten %10 pay), 128x256'ya getirilir ve çok etiketli
sınıflandırıcıya verilir (docs/04 §2). Model, DALSAN sahasından toplanan ve
etiketlenen verilerle eğitilecek (8-9. adım). O zamana kadar:

MODEL YOKSA GÖZLEM DE YOKTUR. Sahte/uydurma karar üretilmez; kural motoru
gözlemsiz pencereyi 'belirsiz' sayar ve ASLA olay üretmez (docs/04 §1).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from app.rules.tipler import KkdGozlem

# Kırpma sözleşmesi (eğitim ve çıkarım AYNI olmalı — docs/04 §2):
CROP_UST_PAY = 0.10  # kutunun üstüne %10 pay (baret kutu dışına taşabilir)
CROP_BOYUT = (128, 256)  # genişlik x yükseklik, portre


def kisi_kirp(kare: np.ndarray, kutu: tuple[float, float, float, float]) -> np.ndarray | None:
    """Kişi kutusunu KKD sözleşmesine göre kırpar. Geçersiz kutuda None."""
    import cv2

    x1, y1, x2, y2 = kutu
    pay = (y2 - y1) * CROP_UST_PAY
    y1 = max(0.0, y1 - pay)
    x1, y1 = int(x1), int(y1)
    x2, y2 = int(min(x2, kare.shape[1])), int(min(y2, kare.shape[0]))
    if x2 - x1 < 4 or y2 - y1 < 8:
        return None
    kirpik = kare[y1:y2, x1:x2]
    return cv2.resize(kirpik, CROP_BOYUT, interpolation=cv2.INTER_LINEAR)


class KkdSiniflandirici:
    """Eğitilmiş model arayüzü. Şimdilik tek gerçek: model dosyası yok.

    Model eğitilince (9. adım) buraya ONNX yüklemesi eklenecek ve
    `degerlendir` gerçek KkdGozlem üretecek. Arayüz şimdiden sabit —
    boru hattı değişmeyecek.
    """

    def __init__(self, model_dosyasi: Path | None = None) -> None:
        self.model_var = model_dosyasi is not None and model_dosyasi.exists()
        self.model_surumu = model_dosyasi.stem if self.model_var else ""

    def degerlendir(self, kirpik: np.ndarray) -> KkdGozlem | None:
        """Model yoksa None: gözlem üretilmedi demektir, 'belirsiz' bile değil.
        Kural motoru gözlemsiz kareyi zaten belirsiz sayar."""
        if not self.model_var:
            return None
        raise NotImplementedError(
            "KKD modeli entegrasyonu 9. adımda: veri toplandıktan ve model "
            "eğitildikten sonra buraya ONNX çıkarımı eklenecek."
        )
