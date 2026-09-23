"""KKD (baret/yelek) sınıflandırıcısı - iki aşamalı yaklaşımın 2. aşaması.

İnsan kutusu kırpılır (üstten %10 pay), 128x256'ya getirilir ve iki başlı
sınıflandırıcıya verilir (docs/04 §2, docs/17 §5.2). Model DALSAN sahasından
toplanıp etiketlenen verilerle ÜRÜN DIŞINDA eğitilir (docs/04 §6); ürüne yalnız
`.onnx` dosyası girer ve zaten kurulu ONNX Runtime ile çalışır.

MODEL YOKSA GÖZLEM DE YOKTUR. Sahte/uydurma karar üretilmez; kural motoru
gözlemsiz pencereyi 'belirsiz' sayar ve ASLA olay üretmez (docs/04 §1).

MODEL SÖZLEŞMESİ (eğitimi yapan uzman buna göre dışa aktarır; docs/04 §6.6):

- girdi: float32 [N, 3, 256, 128]; RGB, 0-1 aralığı (255'e bölünmüş). Ortalama
  ve sapma normalizasyonu MODELİN İÇİNDEDİR: ürün ikinci bir ön işleme
  sözleşmesi taşımaz, iki taraf ayrı normalizasyon yapıp sessizce ayrışamaz.
- çıktı: "baret" ve "yelek" adlı iki çıktı; her biri [N, 3] OLASILIK (softmax
  modelin içinde), sıra [var, yok, görünmüyor].
- bütünlük: `models/SHA256SUMS`'ta dosyanın satırı olmalı. Özet yoksa ya da
  tutmazsa model YÜKLENMEZ (docs/17 §12.5); süpervizör MODEL_LOAD_FAILED yazar.
- kart: ONNX `custom_metadata_map` (sürüm, veri penceresi, test metrikleri…);
  ürün yalnız gösterir.

Sözleşme yüklemede sıfır görüntüyle bir kez denenir: uymayan model yüklenmez.
"""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from pathlib import Path

import numpy as np

from app.analiz.tespit import ModelHatasi
from app.rules.tipler import BELIRSIZ, VAR, YOK, KkdGozlem

# Kırpma sözleşmesi (eğitim ve çıkarım AYNI olmalı - docs/04 §2):
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


def netlik_olc(kirpik: np.ndarray) -> float:
    """Kırpığın netliği: gri tonda Laplacian varyansı (docs/17 §5.3).

    KIRPIK üzerinde ölçülür, kaynak karede değil: model de bu 128x256
    görüntüyü görür. Küçük bir kişiyi büyütmek onu bulanıklaştırır ve bu
    sayı bunu yansıtmalıdır. Hesap burada (OpenCV); "ne kadar bulanık
    belirsizdir" kararı kuralın `min_netlik` parametresinde (rules/).
    """
    import cv2

    gri = cv2.cvtColor(kirpik, cv2.COLOR_BGR2GRAY) if kirpik.ndim == 3 else kirpik
    return float(cv2.Laplacian(gri, cv2.CV_64F).var())


BASLAR = ("baret", "yelek")
# Her başın çıktı sırası; "görünmüyor" kararı belirsizdir (docs/04 §5.2)
SINIF_SIRASI = (VAR, YOK, BELIRSIZ)
_OLASILIK_PAYI = 1e-3  # satır toplamı 1'den bu kadar sapabilir (float32)


def _sha256(yol: Path) -> str:
    ozet = hashlib.sha256()
    with yol.open("rb") as dosya:
        for parca in iter(lambda: dosya.read(1024 * 1024), b""):
            ozet.update(parca)
    return ozet.hexdigest()


def _beklenen_ozet(model_dosyasi: Path) -> str | None:
    """`SHA256SUMS`'taki satır (`<özet>  <dosya adı>`); yoksa None."""
    liste = model_dosyasi.parent / "SHA256SUMS"
    try:
        satirlar = liste.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for satir in satirlar:
        parcalar = satir.split()
        if len(parcalar) == 2 and parcalar[1].lstrip("*") == model_dosyasi.name:
            return parcalar[0].lower()
    return None


def _ort_oturumu(model_dosyasi: Path):
    import onnxruntime

    secenekler = onnxruntime.SessionOptions()
    # Küçük model: tek iş parçacığı yeter, tespit modeliyle çekirdek yarışmaz
    secenekler.intra_op_num_threads = 1
    return onnxruntime.InferenceSession(
        str(model_dosyasi), sess_options=secenekler, providers=["CPUExecutionProvider"]
    )


def _sozlesme_hatasi(model_dosyasi: Path, neden: str) -> ModelHatasi:
    return ModelHatasi(
        f"KKD modeli sözleşmeye uymuyor ({neden}). Modeli veren uzmandan docs/04 §6.6'ya "
        "göre yeniden dışa aktarılmış dosyayı isteyin; o zamana kadar KKD kuralı olay "
        "üretmez.",
        f"KKD modeli sözleşme denetimi: {model_dosyasi} - {neden}",
    )


class KkdSiniflandirici:
    """Eğitilmiş KKD modeli. Dosya yoksa `model_var=False`: gözlem üretilmez.

    Dosya VAR ama doğrulanamıyorsa (özet yok ya da tutmuyor, açılmıyor,
    sözleşmeye uymuyor) `ModelHatasi` fırlatılır: sessizce "model yok" gibi
    davranmak, sahaya konmuş bir modelin neden çalışmadığını gizlerdi.
    Süpervizör hatayı yakalar, MODEL_LOAD_FAILED yazar ve modelsiz devam eder.
    """

    def __init__(
        self,
        model_dosyasi: Path | None = None,
        *,
        oturum_kur: Callable[[Path], object] = _ort_oturumu,
    ) -> None:
        self.model_var = False
        self.model_surumu = ""
        self.kart: dict[str, str] = {}
        self._oturum = None
        self._toplu = False
        if model_dosyasi is None or not model_dosyasi.is_file():
            return
        beklenen = _beklenen_ozet(model_dosyasi)
        if beklenen is None:
            raise ModelHatasi(
                "KKD modeli yüklenmedi: models/SHA256SUMS dosyasında bu modelin özet satırı "
                "yok. Modeli veren uzmandan özet satırını isteyip o dosyaya ekleyin.",
                f"KKD modeli özetsiz: {model_dosyasi}",
            )
        gercek = _sha256(model_dosyasi)
        if gercek != beklenen:
            raise ModelHatasi(
                "KKD modeli yüklenmedi: dosya, models/SHA256SUMS'taki özetle aynı değil "
                "(bozuk ya da farklı bir sürüm). Modeli veren uzmandan doğru dosyayı isteyin.",
                f"KKD modeli özeti tutmadı: {model_dosyasi} - beklenen {beklenen}, dosya {gercek}",
            )
        try:
            oturum = oturum_kur(model_dosyasi)
        except Exception as hata:  # noqa: BLE001 - ORT'nin hata tipleri sürüme göre değişir
            raise ModelHatasi(
                "KKD modeli açılamadı: dosya ONNX Runtime ile okunamıyor. Modeli veren "
                "uzmandan dosyayı yeniden isteyin.",
                f"KKD modeli açılamadı: {model_dosyasi} - {hata!r}",
            ) from hata
        self._oturum = oturum
        self._sozlesmeyi_dogrula(model_dosyasi)
        try:
            self.kart = dict(oturum.get_modelmeta().custom_metadata_map)
        except Exception:  # noqa: BLE001 - kart isteğe bağlı; yoksa yalnız gösterilmez
            self.kart = {}
        self.model_surumu = f"{model_dosyasi.stem}-{gercek[:12]}"
        self.model_var = True

    def _sozlesmeyi_dogrula(self, model_dosyasi: Path) -> None:
        girdiler = self._oturum.get_inputs()
        if len(girdiler) != 1:
            raise _sozlesme_hatasi(model_dosyasi, f"{len(girdiler)} girdi var, 1 olmalı")
        bicim = list(girdiler[0].shape)
        beklenen = [3, CROP_BOYUT[1], CROP_BOYUT[0]]
        if len(bicim) != 4 or any(
            isinstance(b, int) and b != e for b, e in zip(bicim[1:], beklenen, strict=True)
        ):
            raise _sozlesme_hatasi(model_dosyasi, f"girdi biçimi {bicim}, [N, 3, 256, 128] olmalı")
        # N sabit 1 ise kişiler tek tek verilir; değişkense kare başına toplu
        self._toplu = not isinstance(bicim[0], int) or bicim[0] != 1
        adlar = {cikti.name for cikti in self._oturum.get_outputs()}
        if not set(BASLAR) <= adlar:
            raise _sozlesme_hatasi(
                model_dosyasi, f"çıktı adları {sorted(adlar)}; 'baret' ve 'yelek' olmalı"
            )
        sifir = np.zeros((1, 3, CROP_BOYUT[1], CROP_BOYUT[0]), dtype=np.float32)
        try:
            cikti = self._calistir(sifir)
        except Exception as hata:  # noqa: BLE001
            raise _sozlesme_hatasi(model_dosyasi, f"deneme çalıştırması: {hata!r}") from hata
        for bas, degerler in zip(BASLAR, cikti, strict=True):
            if degerler.shape != (1, len(SINIF_SIRASI)):
                raise _sozlesme_hatasi(
                    model_dosyasi, f"'{bas}' çıktısı {degerler.shape}, [N, 3] olmalı"
                )
            if (
                not np.all(np.isfinite(degerler))
                or np.any(degerler < 0)
                or abs(float(degerler.sum()) - 1.0) > _OLASILIK_PAYI
            ):
                raise _sozlesme_hatasi(
                    model_dosyasi, f"'{bas}' olasılık değil (softmax modelin içinde olmalı)"
                )

    def _calistir(self, girdi: np.ndarray) -> list[np.ndarray]:
        girdi_adi = self._oturum.get_inputs()[0].name
        sonuc = self._oturum.run(list(BASLAR), {girdi_adi: girdi})
        return [np.asarray(s, dtype=np.float32) for s in sonuc]

    @staticmethod
    def _girdi(kirpik: np.ndarray) -> np.ndarray:
        """BGR uint8 [256, 128, 3] → RGB float32 [3, 256, 128], 0-1."""
        return np.ascontiguousarray(kirpik[:, :, ::-1].transpose(2, 0, 1), dtype=np.float32) / 255.0

    def degerlendir(self, kirpik: np.ndarray) -> KkdGozlem | None:
        """Model yoksa None: gözlem üretilmedi demektir, 'belirsiz' bile değil.
        Kural motoru gözlemsiz kareyi zaten belirsiz sayar."""
        if not self.model_var:
            return None
        return self.degerlendir_toplu([kirpik])[0]

    def degerlendir_toplu(self, kirpiklar: list[np.ndarray]) -> list[KkdGozlem | None]:
        """Karedeki kişiler tek çağrıda (docs/17 §5.2); model N=1 sabitse tek tek.

        Karar burada VERİLMEZ: her baş için en olası sınıf ve olasılığı yazılır;
        düşük güveni belirsiz sayan eşik kuralın `min_confidence`'ıdır (rules/).
        """
        if not self.model_var or not kirpiklar:
            return [None] * len(kirpiklar)
        girdiler = np.stack([self._girdi(k) for k in kirpiklar])
        if self._toplu:
            baret, yelek = self._calistir(girdiler)
        else:
            parcalar = [self._calistir(girdiler[i : i + 1]) for i in range(len(kirpiklar))]
            baret = np.concatenate([p[0] for p in parcalar])
            yelek = np.concatenate([p[1] for p in parcalar])
        gozlemler = []
        for i, kirpik in enumerate(kirpiklar):
            b, y = int(np.argmax(baret[i])), int(np.argmax(yelek[i]))
            gozlemler.append(
                KkdGozlem(
                    baret=SINIF_SIRASI[b],
                    yelek=SINIF_SIRASI[y],
                    baret_guven=float(baret[i][b]),
                    yelek_guven=float(yelek[i][y]),
                    model_surumu=self.model_surumu,
                    netlik=netlik_olc(kirpik),
                )
            )
        return gozlemler
