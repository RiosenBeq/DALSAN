"""Kamera kaynağı: 'son kare' deseni + otomatik yeniden bağlanma.

RTSP akışı kendi iş parçacığında SÜREKLİ okunur; işlenmeyen kareler atılır.
Aksi halde tampon dolar ve gecikme dakikalara çıkar (docs/02 §6). Analiz
tarafı her zaman en güncel kareyi alır.

Bir kameranın hatası yalnızca kendi iş parçacığını etkiler; üstel bekleme
(1 → 30 sn) ile yeniden bağlanılır. 60 sn kare gelmezse kamera 'offline'
sayılır ve süpervizör sistem olayı üretir.
"""

from __future__ import annotations

import os
import threading
import time

# RTSP'yi TCP üzerinden aç (CLAUDE.md §4): UDP fabrika ağında paket kaybıyla
# bozuk kare üretir. Bu ortam değişkeni OpenCV'nin FFmpeg arkucunu ayarlar ve
# ilk VideoCapture'dan ÖNCE verilmelidir.
os.environ.setdefault("OPENCV_FFMPEG_CAPTURE_OPTIONS", "rtsp_transport;tcp")

import cv2  # noqa: E402  (yukarıdaki ortam değişkeni importtan önce gerekli)
import numpy as np  # noqa: E402

from app.loglama import log_al

# Bağlantı denemeleri arasındaki üstel bekleme sınırları (sn)
_BEKLEME_ILK = 1.0
_BEKLEME_EN_COK = 30.0
# Bu süre kare gelmezse kamera offline kabul edilir (docs/02 §6)
OFFLINE_ESIGI_SN = 60.0


class KameraKaynagi:
    """Tek kameranın okuma iş parçacığı. Yalnızca kare okur; VERİTABANINA
    DOKUNMAZ — durum bilgisini süpervizör okuyup DB'ye yazar."""

    def __init__(self, kamera_id: int, ad: str, kaynak_tipi: str, kaynak_url: str) -> None:
        self.kamera_id = kamera_id
        self.ad = ad
        self.kaynak_tipi = kaynak_tipi  # "rtsp" | "file"
        self.kaynak_url = kaynak_url
        self._log = log_al("kamera")
        self._kilit = threading.Lock()
        self._son_kare: np.ndarray | None = None
        self._son_kare_zamani: float = 0.0  # time.monotonic
        self._kare_sayaci = 0
        self._sayac_baslangici = time.monotonic()
        self.olculen_fps: float = 0.0
        self._dur = threading.Event()
        self._is_parcacigi = threading.Thread(
            target=self._dongu, name=f"kamera-{kamera_id}", daemon=True
        )

    # ---- dış API (süpervizör ve web kullanır) ----

    def baslat(self) -> None:
        self._is_parcacigi.start()

    def durdur(self) -> None:
        self._dur.set()
        self._is_parcacigi.join(timeout=5)

    def son_kare(self) -> tuple[np.ndarray | None, float]:
        """En güncel kare (BGR) ve monotonic zamanı. Kare yoksa (None, 0)."""
        with self._kilit:
            if self._son_kare is None:
                return None, 0.0
            return self._son_kare, self._son_kare_zamani

    def cevrimici_mi(self) -> bool:
        with self._kilit:
            zaman = self._son_kare_zamani
        return zaman > 0 and (time.monotonic() - zaman) < OFFLINE_ESIGI_SN

    # ---- iç döngü ----

    def _dongu(self) -> None:
        bekleme = _BEKLEME_ILK
        while not self._dur.is_set():
            yakalayici = self._ac()
            if yakalayici is None:
                self._log.warning(
                    f"Kamera bağlantısı kurulamadı: {self.ad} — {bekleme:.0f} sn sonra denenecek"
                )
                if self._dur.wait(bekleme):
                    return
                bekleme = min(bekleme * 2, _BEKLEME_EN_COK)
                continue

            bekleme = _BEKLEME_ILK  # bağlantı kuruldu, sayaç sıfırlanır
            self._log.info(f"Kamera bağlandı: {self.ad}")
            dosya_fps = yakalayici.get(cv2.CAP_PROP_FPS) or 0
            try:
                self._okuma_dongusu(yakalayici, dosya_fps)
            finally:
                yakalayici.release()
            if not self._dur.is_set():
                self._log.warning(f"Kamera akışı koptu: {self.ad} — yeniden bağlanılıyor")

    def _ac(self) -> cv2.VideoCapture | None:
        yakalayici = cv2.VideoCapture(self.kaynak_url, cv2.CAP_FFMPEG)
        if not yakalayici.isOpened():
            yakalayici.release()
            return None
        return yakalayici

    def _okuma_dongusu(self, yakalayici: cv2.VideoCapture, dosya_fps: float) -> None:
        while not self._dur.is_set():
            tamam, kare = yakalayici.read()
            if not tamam:
                if self.kaynak_tipi == "file":
                    # Video dosyası kamera taklidi yapar: bitince başa sar (dev/test)
                    yakalayici.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    continue
                return  # RTSP koptu → dış döngü yeniden bağlanır

            simdi = time.monotonic()
            with self._kilit:
                self._son_kare = kare
                self._son_kare_zamani = simdi

            self._kare_sayaci += 1
            gecen = simdi - self._sayac_baslangici
            if gecen >= 10.0:
                self.olculen_fps = self._kare_sayaci / gecen
                self._kare_sayaci = 0
                self._sayac_baslangici = simdi

            if self.kaynak_tipi == "file" and dosya_fps > 0:
                # Dosyayı gerçek hızında oynat; yoksa saniyede yüzlerce kare döner
                if self._dur.wait(1.0 / dosya_fps):
                    return
