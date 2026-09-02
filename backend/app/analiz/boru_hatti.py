"""Kamera başına işleme hattı: tespit → takip → (KKD) → kural motoru → overlay.

Veritabanına DOKUNMAZ; süpervizör konfigürasyonu verir, ihlalleri alıp yazar.
"""

from __future__ import annotations

import threading

import cv2
import numpy as np

from app.analiz.kkd_siniflandirici import KkdSiniflandirici, kisi_kirp
from app.analiz.takip import Takipci
from app.analiz.tespit import SINIF_TR, Tespitci
from app.rules.geometri import nokta_poligonda
from app.rules.motor import KuralMotoru
from app.rules.tipler import SINIF_INSAN, Bolge, Ihlal, Kalibrasyon, Kural, Tespit

# KKD çağrısı seyrek: kişi track'i başına her 5. işlenen karede bir (docs/02 §6)
_KKD_KARE_ARALIGI = 5

# Overlay renkleri (BGR)
_RENKLER = {"person": (80, 200, 80), "truck": (60, 140, 255), "forklift": (0, 200, 255)}
_BOLGE_RENGI = (200, 120, 40)


class KameraHatti:
    def __init__(self, kamera_id: int, fps: int) -> None:
        self.kamera_id = kamera_id
        # Süpervizör, örnekleme hızı değişince hattı yeniden kurmak için okur:
        # ByteTrack'in kare hızı yanlış kalırsa takip hafızası saniye cinsinden
        # kayar ve aynı kişiye ikinci kez uyarı üretilir.
        self.fps = fps
        self._takipci = Takipci(fps)
        self._motor = KuralMotoru(kamera_id)
        self._bolgeler: list[Bolge] = []
        self._kalibrasyon: Kalibrasyon | None = None
        self._kkd_sayac: dict[int, int] = {}  # takip_id -> işlenen kare sayısı
        self._kilit = threading.Lock()
        self._son_jpeg: bytes | None = None

    def yapilandir(
        self, bolgeler: list[Bolge], kurallar: list[Kural], kalibrasyon: Kalibrasyon | None
    ) -> None:
        self._bolgeler = bolgeler
        self._kalibrasyon = kalibrasyon
        self._motor.kurallari_yukle(kurallar)

    def isle(
        self,
        kare: np.ndarray,
        zaman_s: float,
        tespitci: Tespitci | None,
        kkd: KkdSiniflandirici,
    ) -> tuple[list[Tespit], list[Ihlal]]:
        yukseklik, genislik = kare.shape[:2]

        if tespitci is None:
            tespitler: list[Tespit] = []  # model yok — kamera izlenir, tespit yapılmaz
        else:
            kutular, guvenler, siniflar = tespitci.tespit_et(kare)
            tespitler = self._takipci.guncelle(kutular, guvenler, siniflar)

        self._kkd_degerlendir(kare, tespitler, (genislik, yukseklik), kkd)

        ihlaller = self._motor.degerlendir(
            zaman_s,
            (float(genislik), float(yukseklik)),
            tespitler,
            self._bolgeler,
            self._kalibrasyon,
        )

        self._overlay_guncelle(kare, tespitler, ihlaller)
        return tespitler, ihlaller

    def son_islenmis_jpeg(self) -> bytes | None:
        with self._kilit:
            return self._son_jpeg

    def kkd_bolgesinde_mi(self, tespit: Tespit, kare_boyutu: tuple[float, float]) -> bool:
        ayak = tespit.ayak_noktasi()
        ayak_norm = (ayak[0] / kare_boyutu[0], ayak[1] / kare_boyutu[1])
        return any(
            b.tip == "ppe_required" and b.aktif and nokta_poligonda(ayak_norm, b.poligon)
            for b in self._bolgeler
        )

    # ---- iç ----

    def _kkd_degerlendir(
        self,
        kare: np.ndarray,
        tespitler: list[Tespit],
        kare_boyutu: tuple[float, float],
        kkd: KkdSiniflandirici,
    ) -> None:
        if not kkd.model_var:
            return  # gözlem üretilmez; kural motoru belirsiz sayar
        # Kadans sayaçları yalnızca ekranda olan takipler için tutulur;
        # aksi halde sözlük 7x24 çalışmada sınırsız büyürdü.
        mevcutlar = {t.takip_id for t in tespitler}
        self._kkd_sayac = {t: s for t, s in self._kkd_sayac.items() if t in mevcutlar}
        for tespit in tespitler:
            if tespit.sinif != SINIF_INSAN:
                continue
            if not self.kkd_bolgesinde_mi(tespit, kare_boyutu):
                continue
            sayac = self._kkd_sayac.get(tespit.takip_id, 0) + 1
            self._kkd_sayac[tespit.takip_id] = sayac
            if sayac % _KKD_KARE_ARALIGI != 1:
                continue
            kirpik = kisi_kirp(kare, tespit.kutu)
            if kirpik is not None:
                tespit.kkd_gozlemi = kkd.degerlendir(kirpik)

    def _overlay_guncelle(
        self, kare: np.ndarray, tespitler: list[Tespit], ihlaller: list[Ihlal]
    ) -> None:
        gorsel = kare.copy()
        yukseklik, genislik = gorsel.shape[:2]

        for bolge in self._bolgeler:
            if not bolge.aktif:
                continue
            noktalar = np.array([(int(x * genislik), int(y * yukseklik)) for x, y in bolge.poligon])
            cv2.polylines(gorsel, [noktalar], True, _BOLGE_RENGI, 2)

        ihlal_takipleri = {t for ihlal in ihlaller for t in ihlal.takip_idler}
        for tespit in tespitler:
            x1, y1, x2, y2 = (int(v) for v in tespit.kutu)
            renk = (
                (0, 0, 220)
                if tespit.takip_id in ihlal_takipleri
                else _RENKLER.get(tespit.sinif, (180, 180, 180))
            )
            cv2.rectangle(gorsel, (x1, y1), (x2, y2), renk, 2)
            etiket = f"{SINIF_TR.get(tespit.sinif, tespit.sinif)} #{tespit.takip_id}"
            cv2.putText(
                gorsel,
                etiket,
                (x1, max(y1 - 6, 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                renk,
                1,
                cv2.LINE_AA,
            )

        tamam, jpeg = cv2.imencode(".jpg", gorsel, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if tamam:
            with self._kilit:
                self._son_jpeg = jpeg.tobytes()
