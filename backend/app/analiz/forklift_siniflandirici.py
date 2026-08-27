"""Forklift sınıflandırıcısı — docs/08 R1'in ara çözümü.

Hazır dedektör forklifti 'tır' olarak görür. Tam dedektör ince ayarı büyük
eğitim altyapısı ister; en az parçalı yol (CLAUDE.md §3), KKD ile aynı iki
aşamalı desen: dedektörün bulduğu ARAÇ kutusu kırpılır ve /forklift sayfasında
etiketlenen karelerle eğitilmiş küçük bir sınıflandırıcıya sorulur:
"bu araç forklift mi?" Cevap evetse tespitin sınıfı 'forklift' yapılır;
kural motoru, olaylar ve ekran bundan sonrasını zaten bilir.

MODEL YOKSA SINIF DEĞİŞMEZ: araç 'tır' kalır — sahte karar üretilmez.

Model, backend/app/egitim/forklift_egitim.py ile eğitilir ve models/forklift/
altında SÜRÜMLÜ saklanır (docs/04 §9 ilkesi):
    v001.npz  — ağırlıklar + normalizasyon (kırpma/öznitelik sözleşmesiyle uyumlu)
    v001.json — eğitim kaydı (sayılar, isabet karşılaştırması)
    aktif.json — devredeki sürüm + karar eşiği; YOKSA model devrede değildir
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

# Kırpma/öznitelik sözleşmesi: eğitim ve çıkarım AYNI olmalı (docs/04 §2 ilkesi)
CROP_BOYUT = (32, 32)  # genişlik x yükseklik
OZNITELIK_BOYU = CROP_BOYUT[0] * CROP_BOYUT[1] * 3


def arac_kirp(kare: np.ndarray, kutu: tuple[float, float, float, float]) -> np.ndarray | None:
    """Araç kutusunu sınıflandırma sözleşmesine göre kırpar. Geçersiz kutuda None."""
    import cv2

    x1, y1, x2, y2 = kutu
    x1, y1 = max(0, int(x1)), max(0, int(y1))
    x2, y2 = int(min(x2, kare.shape[1])), int(min(y2, kare.shape[0]))
    if x2 - x1 < 8 or y2 - y1 < 8:
        return None
    kirpik = kare[y1:y2, x1:x2]
    return cv2.resize(kirpik, CROP_BOYUT, interpolation=cv2.INTER_LINEAR)


def oznitelik(kirpik: np.ndarray) -> np.ndarray:
    """Kırpık BGR görüntü → düzleştirilmiş [0,1] vektörü (float32)."""
    return (kirpik.astype(np.float32) / 255.0).reshape(-1)


class ForkliftSiniflandirici:
    """models/forklift/aktif.json'daki devredeki modeli yükler ve uygular.

    Eğitim, çalışan sistemi durdurmadan yeni sürümü devreye alabilsin diye
    `gerekirse_yenile` aktif.json değişince modeli yeniden yükler (süpervizör
    bunu 5 sn'lik konfig turunda çağırır — restart yok).
    """

    def __init__(self, model_klasoru: Path) -> None:
        self._klasor = model_klasoru
        self._aktif_damgasi: float | None = None
        self.model_var = False
        self.surum = ""
        self.esik = 0.5
        self._w: np.ndarray | None = None
        self._b = 0.0
        self._ortalama: np.ndarray | None = None
        self._sapma: np.ndarray | None = None
        self._yukle()

    def gerekirse_yenile(self) -> None:
        """aktif.json değiştiyse (yeni sürüm devreye alındıysa) yeniden yükler."""
        aktif = self._klasor / "aktif.json"
        try:
            damga = aktif.stat().st_mtime if aktif.exists() else None
        except OSError:
            damga = None
        if damga != self._aktif_damgasi:
            self._yukle()

    def p_forklift(self, kirpik: np.ndarray) -> float:
        """Kırpık araç görüntüsü için forklift olasılığı (0-1)."""
        return float(self.p_toplu(oznitelik(kirpik)[np.newaxis])[0])

    def p_toplu(self, x: np.ndarray) -> np.ndarray:
        """(n, öznitelik) matrisinde her satır için forklift olasılığı.
        Eğitim, eski modeli yeni modelle AYNI test karelerinde karşılaştırırken
        bunu kullanır."""
        z = ((x - self._ortalama) / self._sapma) @ self._w + self._b
        return 1.0 / (1.0 + np.exp(-np.clip(z, -60.0, 60.0)))

    def forklift_mi(self, kirpik: np.ndarray) -> bool:
        return self.model_var and self.p_forklift(kirpik) >= self.esik

    # ---- iç ----

    def _yukle(self) -> None:
        from app.loglama import log_al

        aktif = self._klasor / "aktif.json"
        self.model_var = False
        try:
            self._aktif_damgasi = aktif.stat().st_mtime if aktif.exists() else None
            if not aktif.exists():
                return  # model henüz devrede değil — sessiz, normal durum
            bilgi = json.loads(aktif.read_text(encoding="utf-8"))
            self.surum = str(bilgi["surum"])
            self.esik = float(bilgi["esik"])
            veri = np.load(self._klasor / f"{self.surum}.npz")
            w = veri["w"]
            if w.shape != (OZNITELIK_BOYU,):
                raise ValueError(f"ağırlık boyutu beklenenden farklı: {w.shape}")
            self._w = w
            self._b = float(veri["b"])
            self._ortalama = veri["ortalama"]
            self._sapma = veri["sapma"]
            self.model_var = True
            log_al("forklift").info(f"Forklift sınıflandırıcısı devrede: {self.surum}")
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as hata:
            # Bozuk model dosyası sistemi durdurmaz: sınıflandırma devre dışı
            # kalır, araçlar 'tır' olarak kalmaya devam eder.
            log_al("forklift").error(f"Forklift modeli yüklenemedi ({self._klasor}): {hata}")
