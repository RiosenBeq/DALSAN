"""Nesne takibi: supervision ByteTrack sarmalayıcısı (kamera başına bir örnek).

Takip, üç şeyin ön koşuludur (docs/01 §3.2): kalıcı track ID ile tekrar
uyarı bastırma, KKD zamansal oylaması ve basit hız tahmini.
"""

from __future__ import annotations

import numpy as np
import supervision as sv

from app.rules.tipler import Tespit

# Sınıf adı ↔ sayı eşlemesi ByteTrack için (yalnızca bu dosyanın içi)
_SINIF_NO = {"person": 0, "truck": 1, "forklift": 2}
_NO_SINIF = {no: ad for ad, no in _SINIF_NO.items()}


class Takipci:
    def __init__(self, fps: int) -> None:
        # track_buffer'ı yüksek tutmak, kısa kayboluşlarda ID'nin korunmasını
        # sağlar → aynı kişiye tekrar uyarı üretme sorununu azaltır (docs/03 §4)
        self._izleyici = sv.ByteTrack(frame_rate=max(fps, 1))

    def guncelle(
        self, kutular: np.ndarray, guvenler: np.ndarray, siniflar: np.ndarray
    ) -> list[Tespit]:
        """Tespitleri takip ID'leriyle eşleyip saf Tespit nesnelerine çevirir."""
        if len(kutular) == 0:
            algilar = sv.Detections.empty()
        else:
            algilar = sv.Detections(
                xyxy=kutular.astype(float),
                confidence=guvenler.astype(float),
                class_id=np.array([_SINIF_NO[s] for s in siniflar]),
            )
        sonuc = self._izleyici.update_with_detections(algilar)

        tespitler: list[Tespit] = []
        for i in range(len(sonuc)):
            takip_id = sonuc.tracker_id[i] if sonuc.tracker_id is not None else None
            if takip_id is None:
                continue  # henüz doğrulanmamış iz — kurallara girmez
            x1, y1, x2, y2 = sonuc.xyxy[i]
            tespitler.append(
                Tespit(
                    sinif=_NO_SINIF[int(sonuc.class_id[i])],
                    kutu=(float(x1), float(y1), float(x2), float(y2)),
                    takip_id=int(takip_id),
                    guven=float(sonuc.confidence[i]) if sonuc.confidence is not None else 0.0,
                )
            )
        return tespitler
