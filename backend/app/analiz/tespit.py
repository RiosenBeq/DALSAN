"""Nesne tespiti: YOLOX (Apache-2.0) + ONNX Runtime.

ADR-002 kararı: AGPL lisanslı Ultralytics YERİNE Apache-2.0 lisanslı YOLOX.
Model, torch'a gerek kalmadan onnxruntime ile çalışır (en az parça).
Model dosyaları repoya girmez; models/indir.sh ile indirilir.

NOT (docs/08 R1): Hazır COCO modellerinde 'forklift' sınıfı YOKTUR. Forklift
çoğu zaman 'truck'/'car' olarak görünür. Gerçek forklift tespiti, sahadan
toplanan görüntülerle ince ayar (3-4. hafta işi) gerektirir. Sınıf eşleme
tablosu bu yüzden tek yerdedir: model değişince yalnızca burası güncellenir.
"""

from __future__ import annotations

import threading
from pathlib import Path

import cv2
import numpy as np

from app.hatalar import DalsanHata
from app.loglama import log_al
from app.rules.tipler import SINIF_INSAN, SINIF_TIR

# COCO sınıf indeksi → bizim sınıf adımız. Listede olmayan sınıflar atılır.
# 5=bus ve 7=truck birlikte "truck" sayılır: sahada ağır araç ayrımı için yeterli.
# 2=car GEÇİCİ olarak araç sayılır: forklift, hazır modelde çoğu zaman car/truck
# görünür (docs/08 R1). Saha verisiyle forklift ince ayarı yapılınca bu satır
# kaldırılır ve gerçek forklift sınıfı eklenir.
MODEL_SINIF_ESLEME: dict[int, str] = {
    0: SINIF_INSAN,
    2: SINIF_TIR,
    5: SINIF_TIR,
    7: SINIF_TIR,
}

# Kullanıcıya görünen Türkçe adlar (arayüz bu tabloyu kullanır)
SINIF_TR = {"person": "insan", "truck": "tır", "forklift": "forklift"}


class ModelHatasi(DalsanHata):
    """Model dosyası yok/bozuk — analiz tespitsiz devam eder, sistem çökmez."""


class Tespitci:
    """YOLOX ONNX modeli. Tek örnek, tüm kameralar paylaşır; oturum çağrısı
    kilitle sıralanır (CPU'da paralel çıkarım zaten hız kazandırmaz)."""

    def __init__(self, model_dosyasi: Path, cihaz: str, guven_esigi: float = 0.35) -> None:
        import onnxruntime  # importu geciktir: model yoksa paket yüklenmesin

        if not model_dosyasi.exists():
            raise ModelHatasi(
                f"Tespit modeli bulunamadı: {model_dosyasi}\n"
                "Çözüm: proje klasöründe models/indir.sh betiğini çalıştırın "
                "(Ana sayfadaki 'Model durumu' kutusunda da yazıyor)."
            )
        saglayicilar = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if cihaz == "cuda"
            else ["CPUExecutionProvider"]
        )
        try:
            self._oturum = onnxruntime.InferenceSession(str(model_dosyasi), providers=saglayicilar)
        except Exception as hata:  # onnxruntime kendi hata tipini garanti etmiyor
            raise ModelHatasi(
                f"Tespit modeli yüklenemedi: {model_dosyasi} — {hata}\n"
                "Dosya bozuk olabilir; models/indir.sh ile yeniden indirin."
            ) from hata
        girdi = self._oturum.get_inputs()[0]
        self._girdi_adi = girdi.name
        # Model girdisinden boyutu oku (tiny: 416, s: 640) — sabit kodlama yok
        self._girdi_boyu = int(girdi.shape[2])
        self.guven_esigi = guven_esigi
        self._kilit = threading.Lock()
        log_al("tespit").info(
            f"Tespit modeli yüklendi: {model_dosyasi.name} "
            f"(girdi {self._girdi_boyu}px, cihaz: {cihaz})"
        )

    def tespit_et(self, kare: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """BGR kare → (kutular_xyxy[piksel], guvenler, sinif_adlari).

        Yalnızca MODEL_SINIF_ESLEME'deki sınıflar döner.
        """
        girdi, oran = self._on_isle(kare)
        with self._kilit:
            cikti = self._oturum.run(None, {self._girdi_adi: girdi})[0]
        return self._son_isle(cikti[0], oran, kare.shape[1], kare.shape[0])

    # ---- YOLOX ön/son işleme (resmi ONNXRuntime demosuyla birebir) ----

    def _on_isle(self, kare: np.ndarray) -> tuple[np.ndarray, float]:
        boy = self._girdi_boyu
        dolgulu = np.full((boy, boy, 3), 114, dtype=np.uint8)
        oran = min(boy / kare.shape[0], boy / kare.shape[1])
        yeni_b = (int(kare.shape[1] * oran), int(kare.shape[0] * oran))
        kucultulmus = cv2.resize(kare, yeni_b, interpolation=cv2.INTER_LINEAR)
        dolgulu[: yeni_b[1], : yeni_b[0]] = kucultulmus
        girdi = dolgulu.transpose(2, 0, 1).astype(np.float32)[np.newaxis]
        return np.ascontiguousarray(girdi), oran

    def _son_isle(
        self, cikti: np.ndarray, oran: float, kare_g: int, kare_y: int
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        # Izgara çözümü: çıktı (N, 85) ham haldedir; merkezler ızgara + adımla açılır
        adimlar = (8, 16, 32)
        izgaralar, adim_dizisi = [], []
        for adim in adimlar:
            kenar = self._girdi_boyu // adim
            xv, yv = np.meshgrid(np.arange(kenar), np.arange(kenar))
            izgara = np.stack((xv, yv), 2).reshape(-1, 2)
            izgaralar.append(izgara)
            adim_dizisi.append(np.full((izgara.shape[0], 1), adim))
        izgaralar = np.concatenate(izgaralar, 0)
        adim_dizisi = np.concatenate(adim_dizisi, 0)

        cikti = cikti.copy()
        cikti[:, :2] = (cikti[:, :2] + izgaralar) * adim_dizisi
        cikti[:, 2:4] = np.exp(cikti[:, 2:4]) * adim_dizisi

        skorlar = cikti[:, 4:5] * cikti[:, 5:]
        sinif_idler = skorlar.argmax(1)
        guvenler = skorlar[np.arange(len(skorlar)), sinif_idler]

        maske = guvenler >= self.guven_esigi
        # Yalnızca ilgilendiğimiz sınıflar
        maske &= np.isin(sinif_idler, list(MODEL_SINIF_ESLEME.keys()))
        if not maske.any():
            bos = np.empty((0,))
            return np.empty((0, 4)), bos, bos.astype(str)

        kutular_cxcywh = cikti[maske, :4] / oran
        guvenler = guvenler[maske]
        sinif_idler = sinif_idler[maske]

        kutular = np.empty_like(kutular_cxcywh)
        kutular[:, 0] = kutular_cxcywh[:, 0] - kutular_cxcywh[:, 2] / 2
        kutular[:, 1] = kutular_cxcywh[:, 1] - kutular_cxcywh[:, 3] / 2
        kutular[:, 2] = kutular_cxcywh[:, 0] + kutular_cxcywh[:, 2] / 2
        kutular[:, 3] = kutular_cxcywh[:, 1] + kutular_cxcywh[:, 3] / 2
        kutular[:, [0, 2]] = kutular[:, [0, 2]].clip(0, kare_g)
        kutular[:, [1, 3]] = kutular[:, [1, 3]].clip(0, kare_y)

        secilenler = cv2.dnn.NMSBoxes(
            [(x1, y1, x2 - x1, y2 - y1) for x1, y1, x2, y2 in kutular.tolist()],
            guvenler.tolist(),
            self.guven_esigi,
            0.45,  # NMS IoU eşiği — YOLOX demosunun varsayılanı
        )
        if len(secilenler) == 0:
            bos = np.empty((0,))
            return np.empty((0, 4)), bos, bos.astype(str)
        secilenler = np.array(secilenler).reshape(-1)

        adlar = np.array([MODEL_SINIF_ESLEME[int(s)] for s in sinif_idler[secilenler]])
        return kutular[secilenler], guvenler[secilenler], adlar
