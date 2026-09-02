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

# İnsan sınıfının model içindeki indeksi — ayrı eşik ve NMS bandı için
_INSAN_MODEL_ID = 0

# Kullanıcıya görünen Türkçe adlar (arayüz bu tabloyu kullanır)
SINIF_TR = {"person": "insan", "truck": "tır", "forklift": "forklift"}


class ModelHatasi(DalsanHata):
    """Model dosyası yok/bozuk — analiz tespitsiz devam eder, sistem çökmez."""


class Tespitci:
    """YOLOX ONNX modeli. Tek örnek, tüm kameralar paylaşır; oturum çağrısı
    kilitle sıralanır (CPU'da paralel çıkarım zaten hız kazandırmaz)."""

    def __init__(
        self,
        model_dosyasi: Path,
        cihaz: str,
        guven_esigi: float = 0.35,
        insan_guven_esigi: float | None = None,
        nms_esigi: float = 0.45,
        en_kucuk_kenar_px: int = 12,
    ) -> None:
        """Eşikler .env'den gelir (CLAUDE.md §7: koda gömülü eşik yasak).

        İnsan eşiği ayrı tutulur: kaçırılan insan, kaçırılan araçtan daha
        risklidir (docs/00), bu yüzden insanda biraz daha cömert davranılır.
        """
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

        # CUDA istendi ama sağlayıcı yoksa onnxruntime SESSİZCE CPU'ya düşer.
        # Ana sayfada "cuda" yazarken CPU'da sürünen sistem, teşhis edilemez
        # bir yavaşlık demektir — durumu dürüstçe sakla (docs/05 ADR-002).
        self.istenen_cihaz = cihaz
        self.etkin_cihaz = (
            "cuda" if "CUDAExecutionProvider" in self._oturum.get_providers() else "cpu"
        )
        self.cihaz_uyarisi = ""
        if cihaz == "cuda" and self.etkin_cihaz != "cuda":
            self.cihaz_uyarisi = (
                "CIKARIM_CIHAZI=cuda seçili ama bu bilgisayarda CUDA çalıştırıcısı yok; "
                "sistem CPU ile çalışıyor (daha yavaş). GPU için NVIDIA sürücüsü ve "
                "onnxruntime-gpu paketi gerekir; ya da .env'de CIKARIM_CIHAZI=cpu yapın."
            )
            log_al("tespit").warning(self.cihaz_uyarisi)

        girdi = self._oturum.get_inputs()[0]
        self._girdi_adi = girdi.name
        # Model girdisinden boyutu oku (tiny: 416, s: 640) — sabit kodlama yok.
        # Dinamik eksenli ('height' gibi) bir dışa aktarımda int() ValueError
        # verirdi; bu ModelHatasi'na çevrilmezse analiz iş parçacığı sessizce ölür.
        try:
            self._girdi_boyu = int(girdi.shape[2])
        except (TypeError, ValueError) as hata:
            raise ModelHatasi(
                f"Model girdi boyutu okunamadı ({model_dosyasi.name}: {girdi.shape}). "
                "Sabit boyutlu bir YOLOX dışa aktarımı gerekir; models/indir.sh ile "
                "resmi model dosyasını indirin."
            ) from hata
        self.guven_esigi = guven_esigi
        # İnsan için ayrı (daha düşük) eşik; verilmezse genel eşik kullanılır
        self.insan_guven_esigi = (
            guven_esigi if insan_guven_esigi is None else min(insan_guven_esigi, guven_esigi)
        )
        self.nms_esigi = nms_esigi
        self.en_kucuk_kenar_px = en_kucuk_kenar_px
        self._kilit = threading.Lock()
        log_al("tespit").info(
            f"Tespit modeli yüklendi: {model_dosyasi.name} "
            f"(girdi {self._girdi_boyu}px, cihaz: {self.etkin_cihaz}, "
            f"eşik {self.guven_esigi:g}/insan {self.insan_guven_esigi:g})"
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

        # SINIF SEÇİMİ: 80 sınıfın tümü üzerinde argmax almak yerine YALNIZCA
        # ilgilendiğimiz sınıflara bakılır. Argmax, bir insanı 0.30 ile 'insan',
        # 0.31 ile 'sırt çantası' bulduğunda insanı tamamen düşürürdü — sahada
        # kaçırılan insan demektir. Sınıf-farkındalıklı seçim, YOLOX'un kendi
        # class-aware yolu ve tespit isabetindeki en büyük kazanç (docs/08 R1).
        ilgi_idler = np.array(sorted(MODEL_SINIF_ESLEME.keys()))
        ilgi_skorlari = skorlar[:, ilgi_idler]
        yerel = ilgi_skorlari.argmax(1)
        sinif_idler = ilgi_idler[yerel]
        guvenler = ilgi_skorlari[np.arange(len(ilgi_skorlari)), yerel]

        # Sınıf başına eşik: insan için daha cömert
        esikler = np.where(sinif_idler == _INSAN_MODEL_ID, self.insan_guven_esigi, self.guven_esigi)
        maske = guvenler >= esikler
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

        # Çok küçük kutular elenir: uzaktaki birkaç piksellik gürültü insan
        # sanılıp yanlış alarm üretmesin (yanlış alarm, kaçırmadan kötüdür).
        kenarlar = np.minimum(kutular[:, 2] - kutular[:, 0], kutular[:, 3] - kutular[:, 1])
        yeterli = kenarlar >= self.en_kucuk_kenar_px
        if not yeterli.any():
            bos = np.empty((0,))
            return np.empty((0, 4)), bos, bos.astype(str)
        kutular, guvenler, sinif_idler = kutular[yeterli], guvenler[yeterli], sinif_idler[yeterli]

        # NMS SINIF FARKINDALIKLI: aynı noktadaki insan ile aracın kutuları
        # birbirini bastırmasın diye sınıflar ayrı koordinat bandına kaydırılır
        # (forklift'in yanındaki insan tam da uyarı üretmesi gereken durumdur).
        kayma = (max(kare_g, kare_y) + 1) * np.array(
            [0 if s == _INSAN_MODEL_ID else 1 for s in sinif_idler], dtype=float
        )
        nms_kutulari = [
            (x1 + k, y1 + k, x2 - x1, y2 - y1)
            for (x1, y1, x2, y2), k in zip(kutular.tolist(), kayma.tolist(), strict=True)
        ]
        secilenler = cv2.dnn.NMSBoxes(
            nms_kutulari,
            guvenler.tolist(),
            # En düşük sınıf eşiğinin biraz altı: NMS'in kendi süzgeci, yukarıda
            # zaten uygulanmış sınıf eşiklerini ikinci kez daraltmasın
            float(min(self.guven_esigi, self.insan_guven_esigi)) * 0.9,
            self.nms_esigi,
        )
        if len(secilenler) == 0:
            bos = np.empty((0,))
            return np.empty((0, 4)), bos, bos.astype(str)
        secilenler = np.array(secilenler).reshape(-1)

        adlar = np.array([MODEL_SINIF_ESLEME[int(s)] for s in sinif_idler[secilenler]])
        return kutular[secilenler], guvenler[secilenler], adlar
