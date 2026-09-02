"""Kamera başına işleme hattı: tespit → takip → (KKD) → kural motoru → overlay.

Veritabanına DOKUNMAZ; süpervizör konfigürasyonu verir, ihlalleri alıp yazar.
"""

from __future__ import annotations

import threading

import cv2
import numpy as np

from app.analiz import goruntu
from app.analiz.kkd_siniflandirici import KkdSiniflandirici, kisi_kirp
from app.analiz.takip import Takipci
from app.analiz.tespit import SINIF_OVERLAY, Tespitci
from app.rules.geometri import nokta_poligonda
from app.rules.motor import KuralMotoru
from app.rules.tipler import (
    SINIF_INSAN,
    VAR,
    YOK,
    Bolge,
    Ihlal,
    Kalibrasyon,
    Kural,
    Tespit,
)


def _yazi(gorsel, metin: str, konum: tuple[int, int], renk, kalinlik: int = 1) -> None:
    """Okunaklı etiket: koyu dış hat + renkli iç. Açık arka planda (beton, kar)
    ince renkli yazı kaybolur; fabrikada ekrana uzaktan bakılır."""
    cv2.putText(
        gorsel,
        metin,
        konum,
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        (20, 20, 20),
        kalinlik + 2,
        cv2.LINE_AA,
    )
    cv2.putText(gorsel, metin, konum, cv2.FONT_HERSHEY_SIMPLEX, 0.55, renk, kalinlik, cv2.LINE_AA)


# KKD çağrısı seyrek: kişi track'i başına her 5. işlenen karede bir (docs/02 §6)
_KKD_KARE_ARALIGI = 5

# Overlay renkleri (BGR). Ekrandaki renk anahtarı (kamera sayfası) bu tabloyla
# BİREBİR aynı olmalı — kullanıcı ekranda gördüğü rengi tanıyabilmeli.
_RENKLER = {
    "person": (80, 200, 80),  # yeşil  — insan
    "forklift": (0, 170, 255),  # turuncu — forklift
    "truck": (255, 140, 60),  # mavi   — tır/araç
}
_IHLAL_RENGI = (0, 0, 220)  # kırmızı — kural ihlali olan nesne
_BOLGE_RENGI = (200, 60, 160)  # mor — araç mavisiyle karışmasın
# KKD göstergeleri: baret beyaz-mavi, reflektörlü yelek SARI (sahadaki yeleğin
# rengiyle aynı olsun ki bakan kişi anında eşleştirsin)
_BARET_RENGI = (255, 200, 60)
_YELEK_RENGI = (0, 220, 245)
_KKD_YOK_RENGI = (0, 0, 220)


class KameraHatti:
    def __init__(self, kamera_id: int, fps: int, iyilestir: bool = False) -> None:
        self.kamera_id = kamera_id
        # Süpervizör, örnekleme hızı değişince hattı yeniden kurmak için okur:
        # ByteTrack'in kare hızı yanlış kalırsa takip hafızası saniye cinsinden
        # kayar ve aynı kişiye ikinci kez uyarı üretilir.
        self.fps = fps
        # Düşük kaliteli kamerada kontrast dengeleme (.env → GORUNTU_IYILESTIRME)
        self.iyilestir = iyilestir
        self._kalite: dict = {"sorun": "yok", "mesaj": ""}
        self._kalite_sayaci = 0
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
        # Kalite ölçümü seyrek: her 50 işlenen karede bir yeter, ölçüm bedava değil
        self._kalite_sayaci += 1
        if self._kalite_sayaci % 50 == 1:
            self._kalite = goruntu.kalite_olc(kare)

        if self.iyilestir:
            # Tespit ve önizleme AYNI kareyi kullanır: kullanıcı ekranda modelin
            # gördüğü görüntüyü görmeli (docs/09 — dürüstlük)
            kare = goruntu.iyilestir(kare)

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

    def kalite(self) -> dict:
        """Son ölçülen görüntü kalitesi (kamera sayfasında gösterilir)."""
        return dict(self._kalite)

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
            ihlalli = tespit.takip_id in ihlal_takipleri
            renk = _IHLAL_RENGI if ihlalli else _RENKLER.get(tespit.sinif, (180, 180, 180))
            cv2.rectangle(gorsel, (x1, y1), (x2, y2), renk, 3 if ihlalli else 2)
            etiket = f"{SINIF_OVERLAY.get(tespit.sinif, tespit.sinif)} #{tespit.takip_id}"
            _yazi(gorsel, etiket, (x1, max(y1 - 6, 12)), renk)
            if tespit.sinif == SINIF_INSAN:
                self._kkd_isaretle(gorsel, tespit, (x1, y1, x2, y2))

        tamam, jpeg = cv2.imencode(".jpg", gorsel, [cv2.IMWRITE_JPEG_QUALITY, 80])
        if tamam:
            with self._kilit:
                self._son_jpeg = jpeg.tobytes()

    def _kkd_isaretle(
        self, gorsel: np.ndarray, tespit: Tespit, kutu: tuple[int, int, int, int]
    ) -> None:
        """Kişinin baret/yelek durumunu kutunun sağ üstüne küçük rozetlerle çizer.

        ÜÇ DURUM gösterilir: var (renkli dolu), yok (kırmızı çapraz), belirsiz
        (gri boş). "Belirsiz" ihlal DEĞİLDİR (docs/04 §1) ve öyle de görünmelidir;
        KKD modeli henüz eğitilmediği sürece tüm kişiler belirsizdir.
        """
        gozlem = tespit.kkd_gozlemi
        if gozlem is None:
            return
        x1, y1, x2, _ = kutu
        for sira, (durum, dolu_renk, harf) in enumerate(
            ((gozlem.baret, _BARET_RENGI, "B"), (gozlem.yelek, _YELEK_RENGI, "Y"))
        ):
            kx = min(x2 - 4, x1 + 4 + sira * 26)
            ky = max(y1 + 4, 4)
            if durum == VAR:
                cv2.rectangle(gorsel, (kx, ky), (kx + 22, ky + 20), dolu_renk, -1)
                _yazi(gorsel, harf, (kx + 6, ky + 15), (20, 20, 20), kalinlik=2)
            elif durum == YOK:
                cv2.rectangle(gorsel, (kx, ky), (kx + 22, ky + 20), _KKD_YOK_RENGI, -1)
                cv2.line(gorsel, (kx + 3, ky + 3), (kx + 19, ky + 17), (255, 255, 255), 2)
                cv2.line(gorsel, (kx + 19, ky + 3), (kx + 3, ky + 17), (255, 255, 255), 2)
            else:  # belirsiz — karar verilemedi, ihlal sayılmaz
                cv2.rectangle(gorsel, (kx, ky), (kx + 22, ky + 20), (150, 150, 150), 1)
                _yazi(gorsel, "?", (kx + 7, ky + 15), (150, 150, 150))
