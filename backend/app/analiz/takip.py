"""Nesne takibi: supervision ByteTrack sarmalayıcısı (kamera başına bir örnek).

Takip, üç şeyin ön koşuludur (docs/01 §3.2): kalıcı track ID ile tekrar
uyarı bastırma, KKD zamansal oylaması ve basit hız tahmini.
"""

from __future__ import annotations

import numpy as np
import supervision as sv

from app.loglama import log_al
from app.rules.tipler import TANINAN_SINIFLAR, Tespit

_log = log_al("takip")

# Sınıf adı ↔ sayı eşlemesi ByteTrack için. Elle yazılmaz, rules/tipler.py'deki
# kanonik listeden TÜRETİLİR: modele yeni bir sınıf eklendiğinde burası da
# kendiliğinden bilir. Eskiden ayrı bir sözlüktü ve unutulduğunda takip
# katmanı her karede KeyError verip o kamerayı kalıcı olarak körleştiriyordu.
_SINIF_NO = {ad: no for no, ad in enumerate(TANINAN_SINIFLAR)}
_NO_SINIF = {no: ad for ad, no in _SINIF_NO.items()}


def kayip_iz_tamponu(hafiza_sn: float) -> int:
    """ByteTrack'in `lost_track_buffer` değeri: hafıza saniyesi × 30.

    supervision bu sayıyı "30 fps'teki kare" olarak yorumlar ve kendi kare
    hızına ölçekler: `max_time_lost = int(frame_rate / 30 × lost_track_buffer)`
    (supervision 0.25.1, byte_tracker/core.py). Yani 6 fps'te 2 sn hafıza →
    tampon 60 → 12 kare = 2 sn. Varsayılan tampon 30 idi: hangi fps olursa
    olsun hafıza 1 sn (docs/17 Olgu 8, K7).
    """
    return max(1, round(hafiza_sn * 30))


class Takipci:
    def __init__(self, fps: int, hafiza_sn: float = 1.0) -> None:
        # Bilinmeyen sınıf uyarısı kamera başına BİR KEZ yazılır; her karede
        # yazılsaydı günlük dosyası saatler içinde okunamaz hale gelirdi.
        self._bildirilen_bilinmeyenler: set[str] = set()
        # Kayıp iz hafızası (.env TAKIP_HAFIZA_SN): kısa bir örtülmede (forklift
        # önünden geçti, kolon arkası) iz aynı kimlikle devam etsin; yoksa aynı
        # kişi yeni bir kimlikle "yeniden" görünür ve kalış sayacı sıfırlanır,
        # uyarı tekrarlar (docs/03 §5). Varsayılan 1 sn eski davranıştır.
        self._izleyici = sv.ByteTrack(
            frame_rate=max(fps, 1), lost_track_buffer=kayip_iz_tamponu(hafiza_sn)
        )

    def _bilinmeyeni_bildir(self, adlar) -> None:
        yeniler = {str(a) for a in adlar} - self._bildirilen_bilinmeyenler
        if not yeniler:
            return
        self._bildirilen_bilinmeyenler |= yeniler
        _log.warning(
            "Tespit modeli tanınmayan sınıf üretti, bu tespitler atlanıyor: "
            + ", ".join(sorted(yeniler))
            + ". Sınıfın sisteme tanıtılması gerekir "
            "(backend/app/rules/tipler.py → TANINAN_SINIFLAR)."
        )

    def guncelle(
        self, kutular: np.ndarray, guvenler: np.ndarray, siniflar: np.ndarray
    ) -> list[Tespit]:
        """Tespitleri takip ID'leriyle eşleyip saf Tespit nesnelerine çevirir."""
        # Tanınmayan sınıf ATLANIR, çökmez: kural motoru zaten yalnızca bildiği
        # sınıflarla çalışır ve bir kameranın körleşmesi, o nesneyi kaçırmaktan
        # kat kat kötüdür. Durum sessiz kalmasın diye bir kez günlüğe yazılır.
        bilinen = np.array([s in _SINIF_NO for s in siniflar], dtype=bool)
        if len(bilinen) and not bilinen.all():
            self._bilinmeyeni_bildir(siniflar[~bilinen])
            kutular, guvenler, siniflar = (
                kutular[bilinen],
                guvenler[bilinen],
                siniflar[bilinen],
            )

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
                continue  # henüz doğrulanmamış iz - kurallara girmez
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
