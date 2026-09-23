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

import json
import threading
from importlib import metadata
from pathlib import Path

import cv2
import numpy as np

from app.analiz.model_adi import MARKA, gorunen_model_adi
from app.hatalar import DalsanHata
from app.loglama import log_al
from app.rules.tipler import SINIF_FORKLIFT, SINIF_INSAN, SINIF_TIR, TANINAN_SINIFLAR

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

# Kendi eğittiğimiz modelde (forklift sınıfıyla) sınıf listesi dosyanın
# İÇİNDEDİR (docs/17 §4.2): eğitim betiği ONNX `custom_metadata_map`'e bu
# anahtarla çıkış indeksi → katalog kodu yazar. Hazır YOLOX'ta üst veri boştur
# ve yukarıdaki COCO eşlemesi kullanılır.
UST_VERI_SINIF_ANAHTARI = "dalsan_classes"


def sinif_eslemesi(ust_veri: dict[str, str]) -> tuple[dict[int, str], list[str]]:
    """Model çıkış indeksi → katalog kodu ve katalogda olmayan kodlar.

    Üst veride JSON liste (sıra = çıkış indeksi) ya da {"indeks": "kod"}
    sözlüğü kabul edilir; birden çok indeks aynı koda gidebilir (car ve truck
    → truck). Katalogda (TANINAN_SINIFLAR) olmayan kod atlanır ve bildirilir.
    Okunamayan liste ModelHatasi'dır: yanlış sırayla okunan bir model forklifti
    insan, insanı forklift sanabilirdi.
    """
    ham = ust_veri.get(UST_VERI_SINIF_ANAHTARI)
    if not ham:
        return dict(MODEL_SINIF_ESLEME), []
    try:
        veri = json.loads(ham)
        if isinstance(veri, list):
            ciftler = list(enumerate(veri))
        elif isinstance(veri, dict):
            ciftler = [(int(indeks), kod) for indeks, kod in veri.items()]
        else:
            raise ValueError("liste ya da sözlük değil")
    except (ValueError, TypeError) as hata:
        raise ModelHatasi(
            "Tespit modelinin sınıf listesi okunamadı. Kendi eğittiğiniz modeli "
            "kullanıyorsanız program klasöründeki veri/loglar/sistem.log dosyasını "
            "destek ekibine iletin; hazır modele dönmek için .env'deki MODEL_DOSYASI "
            "satırını .env.example'daki gibi düzeltin.",
            f"ONNX üst verisi {UST_VERI_SINIF_ANAHTARI} çözülemedi: {ham!r} ({hata})",
        ) from hata
    esleme: dict[int, str] = {}
    bilinmeyen: list[str] = []
    for indeks, kod in ciftler:
        if kod in TANINAN_SINIFLAR:
            esleme[int(indeks)] = kod
        else:
            bilinmeyen.append(str(kod))
    if not esleme:
        raise ModelHatasi(
            "Tespit modeli insan, forklift ya da tır sınıflarından hiçbirini tanımıyor; "
            "bu modelle güvenlik kuralları çalışamaz. Hazır modele dönmek için .env'deki "
            "MODEL_DOSYASI satırını .env.example'daki gibi düzeltin.",
            f"ONNX üst verisi {UST_VERI_SINIF_ANAHTARI}: {ham!r}",
        )
    return esleme, bilinmeyen


# Kullanıcıya görünen Türkçe adlar (arayüz bu tabloyu kullanır)
SINIF_TR = {"person": "insan", "truck": "tır", "forklift": "forklift"}

# GÖRÜNTÜ ÜZERİNE yazılan adlar. cv2.putText yalnızca ASCII çizer; Türkçe
# harfler "?" olur ("tır" → "t?r"). Yeni bir yazı tipi kütüphanesi eklemek
# yerine (CLAUDE.md §3: en az parça) overlay'de ASCII karşılıkları kullanılır.
# Ekrandaki metinler, tablolar ve renk anahtarı tam Türkçe kalır.
SINIF_OVERLAY = {"person": "insan", "truck": "tir", "forklift": "forklift"}


class ModelHatasi(DalsanHata):
    """Model dosyası yok/bozuk - analiz tespitsiz devam eder, sistem çökmez."""


def _ort_paketleri() -> list[str]:
    """Kurulu ONNX Runtime paketleri. İKİSİ birden kuruluysa GPU sessizce kaybolur.

    onnxruntime (CPU) ile onnxruntime-gpu aynı `onnxruntime` modülünü yazar;
    birlikte kurulduklarında hangisinin dosyalarının kaldığı kurulum sırasına
    bağlıdır ve CUDA çoğu zaman görünmez olur (docs/16 §5). pip bunu
    engellemez: GPU tekerleği CPU paketini "sağladığını" bildirmiyor.
    """
    kurulu = []
    for ad in ("onnxruntime", "onnxruntime-gpu"):
        try:
            metadata.distribution(ad)
        except metadata.PackageNotFoundError:
            continue
        kurulu.append(ad)
    return kurulu


def _acilamadi(model_dosyasi: Path, hata: Exception) -> ModelHatasi:
    """Model CPU'da da açılmadı: dosya mı bozuk, kurulum mu? Ekrana doğrusu çıkar.

    Açılmayan bir model için "dosya bozuk" demek her zaman doğru değildir:
    dosya resmi yayınla aynıysa (SHA-256) sorun kurulumdadır ve dosyayı
    değiştirmek hiçbir şeyi düzeltmez. Kendi eğitilmiş model için
    karşılaştırılacak özet yoktur; o zaman bozuk varsayılır.
    """
    from app.analiz.model_indir import resmi_yayinla_ayni_mi

    ad = gorunen_model_adi(model_dosyasi.name)
    teknik = f"Tespit modeli yüklenemedi: {model_dosyasi} - {hata!r}"
    if resmi_yayinla_ayni_mi(model_dosyasi):
        return ModelHatasi(
            f"{ad} açılamadı ama model dosyası sağlam (doğrulandı): sorun programın "
            "kurulumunda. Kontrol Paneli'nde 'İlk Kurulumu Yap' düğmesi varsa ona basın, "
            "yoksa programı yeniden kurun; sonra Sistemi Başlat'a basın. Düzelmezse "
            "program klasöründeki veri/loglar/sistem.log dosyasını destek ekibine iletin.",
            f"{teknik} | dosyanın SHA-256 özeti resmi yayınla aynı: dosya sağlam",
        )
    # Bozuk dosya yerinde DURDUĞU için yeniden başlatmak tek başına yetmeyebilir
    # (dosya varsa indirme atlanır). Mesaj bunu saklamaz: önce ucuz olanı
    # söyler, sonra kesin çözüm yolunu gösterir.
    return ModelHatasi(
        f"{ad} açılamadı: dosyası bozuk. "
        "Kontrol Paneli'nde Durdur'a, sonra Sistemi Başlat'a basın. Düzelmezse "
        "bozuk dosyanın değiştirilmesi gerekir: program klasöründeki "
        "veri/loglar/sistem.log dosyasını destek ekibine iletin.",
        teknik,
    )


class Tespitci:
    """YOLOX ONNX modeli. Tek örnek, tüm kameralar paylaşır; oturum çağrısı
    kilitle sıralanır (CPU'da paralel çıkarım zaten hız kazandırmaz)."""

    # Hazır YOLOX'un (COCO) eşlemesi; özel model __init__'te üst veriden kurar
    _sinif_esleme: dict[int, str] = MODEL_SINIF_ESLEME
    _insan_model_id = 0
    siniflar: tuple[str, ...] = (SINIF_INSAN, SINIF_TIR)
    forklift_taniyor = False

    def __init__(
        self,
        model_dosyasi: Path,
        cihaz: str,
        guven_esigi: float = 0.35,
        insan_guven_esigi: float | None = None,
        nms_esigi: float = 0.45,
        en_kucuk_kenar_px: int = 12,
        is_parcacigi: int = 0,
    ) -> None:
        """Eşikler .env'den gelir (CLAUDE.md §7: koda gömülü eşik yasak).

        İnsan eşiği ayrı tutulur: kaçırılan insan, kaçırılan araçtan daha
        risklidir (docs/00), bu yüzden insanda biraz daha cömert davranılır.
        """
        import onnxruntime  # importu geciktir: model yoksa paket yüklenmesin

        if not model_dosyasi.exists():
            # Ekranda ürün adı ve YAPILABİLİR bir adım; tam dosya yolu günlüğe
            # gider (CLAUDE.md §8 - kullanıcıya terminal komutu verilmez).
            raise ModelHatasi(
                f"{gorunen_model_adi(model_dosyasi.name)} kurulu değil. Kontrol Paneli'nde "
                f"Durdur'a, sonra Sistemi Başlat'a basın - {MARKA} ilk açılışta kendiliğinden "
                "iner. Sorun sürerse program klasöründeki veri/loglar/sistem.log dosyasını "
                "destek ekibine iletin.",
                f"Tespit modeli bulunamadı: {model_dosyasi}",
            )
        saglayicilar = (
            ["CUDAExecutionProvider", "CPUExecutionProvider"]
            if cihaz == "cuda"
            else ["CPUExecutionProvider"]
        )
        secenekler = onnxruntime.SessionOptions()
        # BEKLERKEN DÖNME KAPALI. ONNX Runtime'ın iş parçacıkları her
        # çıkarımdan sonra bir süre boşta DÖNEREK (spinning) yeni iş bekler.
        # Kamera saniyede 6 kare verdiği için aradaki bekleme uzundur ve bu
        # dönme işlemciyi boşa yakar. Ölçüm (yolox_tiny, 4 çekirdek, saniyede
        # 6 çıkarım): dönme açıkken CPU %115, kapalıyken %58; gecikme p50
        # 26 → 36 ms. Dört kamerada iş parçacıkları zaten meşgul olduğundan
        # verim değişmez (tests/hiz_kiyas --dort, docs/ILERLEME).
        secenekler.add_session_config_entry("session.intra_op.allow_spinning", "0")
        secenekler.add_session_config_entry("session.inter_op.allow_spinning", "0")
        # 0 = ONNX Runtime kendi seçer (tüm çekirdekler). Sunucu başka işler de
        # yapıyorsa .env'den sınırlanır; tek kamerada bile fark eder, çünkü
        # tespit TÜM kameralar için tek oturumda ve kilitle sıralı çalışır:
        # bir çıkarım makinenin tamamını meşgul edebilir.
        if is_parcacigi > 0:
            secenekler.intra_op_num_threads = is_parcacigi
            secenekler.inter_op_num_threads = 1
        ek_argumanlar = {"sess_options": secenekler}
        # Kurulan GPU sağlayıcısı hatası ile bozuk dosya AYRI şeylerdir (docs/17
        # §13, 2a). Önceden ikisi de "dosya bozuk" diye bildiriliyordu:
        # kullanıcı sağlam bir dosyayı değiştirmeye uğraşırken asıl sorun
        # sürücüdeydi. Aynı dosya yalnız CPU ile açılıyorsa sorun GPU'dadır.
        gpu_hatasi = None
        try:
            self._oturum = onnxruntime.InferenceSession(
                str(model_dosyasi), providers=saglayicilar, **ek_argumanlar
            )
        except Exception as hata:  # onnxruntime kendi hata tipini garanti etmiyor
            if saglayicilar == ["CPUExecutionProvider"]:
                raise _acilamadi(model_dosyasi, hata) from hata
            try:
                self._oturum = onnxruntime.InferenceSession(
                    str(model_dosyasi), providers=["CPUExecutionProvider"], **ek_argumanlar
                )
            except Exception as cpu_hatasi:
                raise _acilamadi(model_dosyasi, cpu_hatasi) from cpu_hatasi
            gpu_hatasi = hata

        # CUDA istendi ama sağlayıcı yoksa onnxruntime SESSİZCE CPU'ya düşer.
        # Ana sayfada "cuda" yazarken CPU'da sürünen sistem, teşhis edilemez
        # bir yavaşlık demektir - durumu dürüstçe sakla (docs/05 ADR-002).
        self.istenen_cihaz = cihaz
        self.etkin_cihaz = (
            "cuda" if "CUDAExecutionProvider" in self._oturum.get_providers() else "cpu"
        )
        self.cihaz_uyarisi = ""
        paketler = _ort_paketleri()
        cakisma = len(paketler) > 1
        # /saglik "ort_paket_cakismasi" (docs/17 §9.1): sistem çalışır ama GPU
        # sessizce kaybolabilir.
        self.ort_paket_cakismasi = cakisma
        if cakisma:
            log_al("tespit").warning(
                "İki ONNX Runtime paketi birlikte kurulu (onnxruntime ve onnxruntime-gpu): "
                "GPU sessizce kaybolabilir. İkisini de kaldırıp yalnız birini kurun."
            )
        if cihaz == "cuda" and self.etkin_cihaz != "cuda":
            if gpu_hatasi is not None:
                sebep = (
                    "GPU çalıştırıcısı başlatılamadı (NVIDIA sürücüsü ya da CUDA sürümü "
                    "uyumsuz olabilir)"
                )
            elif cakisma:
                sebep = (
                    "CPU ve GPU çalışma zamanı paketleri birlikte kurulu; GPU paketinin "
                    "çalışması için CPU paketinin kaldırılması gerekir"
                )
            else:
                sebep = "bu bilgisayarda CUDA çalıştırıcısı yok"
            self.cihaz_uyarisi = (
                f"CIKARIM_CIHAZI=cuda seçili ama {sebep}; sistem CPU ile çalışıyor "
                "(daha yavaş). GPU için NVIDIA sürücüsü ve onnxruntime-gpu paketi gerekir; "
                "ya da .env'de CIKARIM_CIHAZI=cpu yapın."
            )
            ek = {"extra": {"ayrinti": f"GPU oturum hatası: {gpu_hatasi!r}"}} if gpu_hatasi else {}
            log_al("tespit").warning(self.cihaz_uyarisi, **ek)

        # Sınıf listesi: özel modelde dosyanın üst verisinden, hazırda COCO
        try:
            ust_veri = dict(self._oturum.get_modelmeta().custom_metadata_map or {})
        except AttributeError:  # üst verisi okunamayan oturum: hazır model gibi
            ust_veri = {}
        self._sinif_esleme, bilinmeyen = sinif_eslemesi(ust_veri)
        if bilinmeyen:
            log_al("tespit").warning(
                "Modelin şu sınıfları sistemde tanımlı değil ve atlanıyor: " + ", ".join(bilinmeyen)
            )
        insan_idleri = sorted(i for i, kod in self._sinif_esleme.items() if kod == SINIF_INSAN)
        # İnsan yoksa -1: hiçbir çıkış indeksi insan eşiğine ve bandına düşmez
        self._insan_model_id = insan_idleri[0] if insan_idleri else -1
        # Modelin ürettiği katalog sınıfları; kurulum listesi forklifti buradan söyler
        self.siniflar = tuple(k for k in TANINAN_SINIFLAR if k in self._sinif_esleme.values())
        self.forklift_taniyor = SINIF_FORKLIFT in self.siniflar

        girdi = self._oturum.get_inputs()[0]
        self._girdi_adi = girdi.name
        # Model girdisinden boyutu oku (tiny: 416, s: 640) - sabit kodlama yok.
        # Dinamik eksenli ('height' gibi) bir dışa aktarımda int() ValueError
        # verirdi; bu ModelHatasi'na çevrilmezse analiz iş parçacığı sessizce ölür.
        try:
            self._girdi_boyu = int(girdi.shape[2])
        except (TypeError, ValueError) as hata:
            raise ModelHatasi(
                f"{gorunen_model_adi(model_dosyasi.name)} bu sistemle uyumlu değil. Hazır "
                "modele dönmek için: program klasöründeki .env dosyasını bir metin "
                "düzenleyiciyle açın, MODEL_DOSYASI ile başlayan satırı yanındaki "
                ".env.example dosyasında yazdığı gibi düzeltip kaydedin, sonra Kontrol "
                "Paneli'nde Durdur'a ve Sistemi Başlat'a basın. Kendi eğittiğiniz modeli "
                "kullanmak istiyorsanız program klasöründeki veri/loglar/sistem.log "
                "dosyasını destek ekibine iletin.",
                f"Model girdi boyutu okunamadı ({model_dosyasi}: girdi biçimi {girdi.shape}).",
            ) from hata
        self.guven_esigi = guven_esigi
        # İnsan için ayrı (daha düşük) eşik; verilmezse genel eşik kullanılır
        self.insan_guven_esigi = (
            guven_esigi if insan_guven_esigi is None else min(insan_guven_esigi, guven_esigi)
        )
        self.nms_esigi = nms_esigi
        self.en_kucuk_kenar_px = en_kucuk_kenar_px
        self._kilit = threading.Lock()
        # Kontrol Paneli günlüğünde ürün adı görünür; dosya adı ve tam yol
        # yalnızca veri/loglar/sistem.log'daki `ayrinti` alanına düşer.
        log_al("tespit").info(
            f"{gorunen_model_adi(model_dosyasi.name)} yüklendi "
            f"(girdi {self._girdi_boyu}px, cihaz: {self.etkin_cihaz}, "
            f"eşik {self.guven_esigi:g}/insan {self.insan_guven_esigi:g})",
            extra={"ayrinti": f"model dosyası: {model_dosyasi}"},
        )

    def tespit_et(self, kare: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """BGR kare → (kutular_xyxy[piksel], guvenler, sinif_adlari).

        Yalnızca modelin sınıf eşlemesindeki (üst veri ya da COCO) sınıflar döner.
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
        # 0.31 ile 'sırt çantası' bulduğunda insanı tamamen düşürürdü - sahada
        # kaçırılan insan demektir. Sınıf-farkındalıklı seçim, YOLOX'un kendi
        # class-aware yolu ve tespit isabetindeki en büyük kazanç (docs/08 R1).
        ilgi_idler = np.array(sorted(self._sinif_esleme.keys()))
        ilgi_skorlari = skorlar[:, ilgi_idler]
        yerel = ilgi_skorlari.argmax(1)
        sinif_idler = ilgi_idler[yerel]
        guvenler = ilgi_skorlari[np.arange(len(ilgi_skorlari)), yerel]

        # Sınıf başına eşik: insan için daha cömert
        esikler = np.where(
            sinif_idler == self._insan_model_id, self.insan_guven_esigi, self.guven_esigi
        )
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
            [0 if s == self._insan_model_id else 1 for s in sinif_idler], dtype=float
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

        adlar = np.array([self._sinif_esleme[int(s)] for s in sinif_idler[secilenler]])
        return kutular[secilenler], guvenler[secilenler], adlar
