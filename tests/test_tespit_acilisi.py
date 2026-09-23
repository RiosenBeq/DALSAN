"""Tespit modeli açılışı: GPU sağlayıcısı hatası ≠ bozuk dosya (docs/17 §13, 2a).

Eskiden `InferenceSession` her hatada "dosyası bozuk" deniyordu. CUDA seçiliyken
sürücü uyumsuzluğu da oturumu düşürür; kullanıcı sağlam bir dosyayı
değiştirmeye uğraşırken asıl sorun sürücüde kalırdı. Oturum sahtedir: testler
gerçek model dosyasına (depoda yok) ve GPU'ya bağlı değildir.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import onnxruntime
import pytest

from app.analiz import model_indir, tespit
from app.analiz.tespit import ModelHatasi, Tespitci

KOK = Path(__file__).resolve().parents[1]


class _SahteOturum:
    """CUDA istenirse çöker (sürücü yok), yalnız CPU ile açılır.

    Açılıştaki deneme çalıştırması (sözleşme sınaması) için `run`, 416'lık
    girdinin 3549 satırını ve `sinif_sayisi` kadar sınıf sütununu döndürür.
    """

    sinif_sayisi = 80

    def __init__(self, yol, providers, **_):
        if "CUDAExecutionProvider" in providers:
            raise RuntimeError("CUDA sağlayıcısı başlatılamadı: libcudnn.so.9 bulunamadı")
        self._saglayicilar = list(providers)

    def get_providers(self):
        return self._saglayicilar

    def get_inputs(self):
        return [SimpleNamespace(name="images", shape=[1, 3, 416, 416])]

    def run(self, _adlar, _besleme):
        return [np.zeros((1, 3549, 5 + self.sinif_sayisi), dtype=np.float32)]


def _hep_coken(*_, **__):
    raise RuntimeError("[ONNXRuntimeError] : 7 : INVALID_PROTOBUF : Load model failed")


@pytest.fixture
def model(tmp_path):
    yol = tmp_path / "models" / "yolox_tiny.onnx"
    yol.parent.mkdir()
    yol.write_bytes(b"model-baytlari" * 100)
    return yol


def test_gpu_saglayicisi_coker_ama_dosya_saglamsa_cpu_ile_calisir(model, monkeypatch):
    monkeypatch.setattr(onnxruntime, "InferenceSession", _SahteOturum)
    monkeypatch.setattr(tespit, "_ort_paketleri", lambda: ["onnxruntime-gpu"])
    tespitci = Tespitci(model, "cuda")
    assert tespitci.etkin_cihaz == "cpu"
    assert "GPU çalıştırıcısı başlatılamadı" in tespitci.cihaz_uyarisi
    assert "bozuk" not in tespitci.cihaz_uyarisi


def test_cpu_da_acilmayan_ama_ozeti_tutan_dosya_bozuk_sayilmaz(model, monkeypatch):
    """Dosya resmi yayınla aynıysa sorun kurulumdadır; "dosya bozuk" demek
    kullanıcıyı sağlam dosyayı değiştirmeye yollardı."""
    monkeypatch.setattr(onnxruntime, "InferenceSession", _hep_coken)
    monkeypatch.setitem(
        model_indir.BILINEN_MODELLER, model.name, hashlib.sha256(model.read_bytes()).hexdigest()
    )
    with pytest.raises(ModelHatasi) as hata:
        Tespitci(model, "cpu")
    assert "sağlam" in hata.value.kullanici_mesaji
    assert "bozuk" not in hata.value.kullanici_mesaji
    assert str(model) in hata.value.teknik_ayrinti


def test_ozeti_tutmayan_dosya_bozuk_sayilir(model, monkeypatch):
    monkeypatch.setattr(onnxruntime, "InferenceSession", _hep_coken)
    with pytest.raises(ModelHatasi) as hata:
        Tespitci(model, "cuda")  # GPU denemesi de CPU denemesi de düşer
    assert "dosyası bozuk" in hata.value.kullanici_mesaji


def test_iki_calisma_zamani_paketi_birlikteyse_sebep_soylenir(model, monkeypatch):
    """onnxruntime ve onnxruntime-gpu aynı modülü yazar; birlikte kurulunca
    CUDA sessizce kaybolur ve pip bunu engellemez."""

    class _YalnizCpu(_SahteOturum):
        def __init__(self, yol, providers, **_):
            self._saglayicilar = ["CPUExecutionProvider"]

    monkeypatch.setattr(onnxruntime, "InferenceSession", _YalnizCpu)
    monkeypatch.setattr(tespit, "_ort_paketleri", lambda: ["onnxruntime", "onnxruntime-gpu"])
    tespitci = Tespitci(model, "cuda")
    assert "birlikte kurulu" in tespitci.cihaz_uyarisi


def test_kurulu_paket_listesi_gercek_ortami_okur():
    assert "onnxruntime" in tespit._ort_paketleri()


# ------------------------------------------------ sınıf listesi (docs/17 §4.2)


def test_ust_veri_yoksa_hazir_coco_eslemesi():
    esleme, bilinmeyen = tespit.sinif_eslemesi({})
    assert esleme == tespit.MODEL_SINIF_ESLEME and bilinmeyen == []
    assert "forklift" not in esleme.values(), "hazır modelde forklift sınıfı yok (docs/08 R1)"


@pytest.mark.parametrize(
    "ham",
    ['["person", "forklift", "truck"]', '{"0": "person", "1": "forklift", "2": "truck"}'],
)
def test_ust_verideki_sinif_listesi_okunur(ham):
    esleme, bilinmeyen = tespit.sinif_eslemesi({"dalsan_classes": ham})
    assert esleme == {0: "person", 1: "forklift", 2: "truck"} and bilinmeyen == []


def test_katalogda_olmayan_sinif_atlanir_ve_bildirilir():
    ham = '["person", "forklift", "pallet_truck", "truck", "truck"]'
    esleme, bilinmeyen = tespit.sinif_eslemesi({"dalsan_classes": ham})
    assert esleme == {0: "person", 1: "forklift", 3: "truck", 4: "truck"}
    assert bilinmeyen == ["pallet_truck"]


@pytest.mark.parametrize("ham", ["{bozuk", '"person"', '["pallet_truck"]'])
def test_okunamayan_ya_da_bos_liste_modeli_acmaz(ham):
    with pytest.raises(ModelHatasi):
        tespit.sinif_eslemesi({"dalsan_classes": ham})


class _UstVeriliOturum(_SahteOturum):
    sinif_sayisi = 3

    def get_modelmeta(self):
        return SimpleNamespace(
            custom_metadata_map={"dalsan_classes": '["person", "forklift", "truck"]'}
        )


def test_forklift_sinifli_model_yuklenince_sistem_bunu_bilir(model, monkeypatch):
    monkeypatch.setattr(onnxruntime, "InferenceSession", _UstVeriliOturum)
    monkeypatch.setattr(tespit, "_ort_paketleri", lambda: ["onnxruntime"])
    tespitci = Tespitci(model, "cpu")
    assert tespitci.forklift_taniyor
    assert tespitci.siniflar == ("person", "truck", "forklift")
    assert tespitci._insan_model_id == 0


def test_hazir_modelde_forklift_ayri_sinif_degil(model, monkeypatch):
    monkeypatch.setattr(onnxruntime, "InferenceSession", _SahteOturum)
    monkeypatch.setattr(tespit, "_ort_paketleri", lambda: ["onnxruntime"])
    tespitci = Tespitci(model, "cpu")
    assert not tespitci.forklift_taniyor
    assert tespitci.siniflar == ("person", "truck")


# ------------------------------------------------ açılışta sözleşme sınaması


def _oturum(cikti=None, bicim=(1, 3, 416, 416), ust_veri=None, hata=None):
    """İstenen çıktıyı veren sahte oturum sınıfı (deneme çalıştırması için)."""

    class _Oturum(_SahteOturum):
        def get_inputs(self):
            return [SimpleNamespace(name="images", shape=list(bicim))]

        def get_modelmeta(self):
            return SimpleNamespace(custom_metadata_map=dict(ust_veri or {}))

        def run(self, _adlar, _besleme):
            if hata is not None:
                raise hata
            if cikti is not None:
                return [cikti]
            return super().run(_adlar, _besleme)

    return _Oturum


def _cikti(sinif=80, satir=3549):
    return np.zeros((1, satir, 5 + sinif), dtype=np.float32)


def _cozulmus():
    cikti = _cikti()
    cikti[0, :, :2] = 200.0  # ızgara çözümü modelin içinde yapılmış: merkezler piksel
    return cikti


def _sigmoidsiz():
    cikti = _cikti()
    cikti[0, 10, 5] = 3.5
    return cikti


def _nan():
    cikti = _cikti()
    cikti[0, 0, 0] = np.nan
    return cikti


@pytest.mark.parametrize(
    ("oturum", "sebep"),
    [
        (_oturum(cikti=_cozulmus()), "kutular ham değil"),
        (_oturum(cikti=_cikti(satir=8400)), "çıktı biçimi"),
        (_oturum(cikti=_cikti(sinif=3)), "80 sınıflı"),
        (
            _oturum(
                cikti=_cikti(sinif=3), ust_veri={"dalsan_classes": '["person", "a", "b", "truck"]'}
            ),
            "sınıf listesi",
        ),
        (
            _oturum(cikti=_cikti(sinif=2), ust_veri={"dalsan_classes": '["forklift", "truck"]'}),
            "insan",
        ),
        (_oturum(cikti=_sigmoidsiz()), "puanlar"),
        (_oturum(cikti=_nan()), "sonlu"),
        (_oturum(bicim=(1, 3, 416, 640)), "girdi biçimi"),
        (_oturum(bicim=(1, 3, 400, 400)), "32'nin katı"),
        (_oturum(hata=RuntimeError("Got invalid dimensions for input")), "deneme çalıştırması"),
    ],
)
def test_sozlesmeye_uymayan_model_acilista_reddedilir(model, monkeypatch, oturum, sebep):
    """Yanlış dışa aktarılmış model eskiden her karede ayrı hata veriyor, ana
    sayfa onu "hazır" gösteriyordu. Şimdi açılışta, anlaşılır bir mesajla
    reddedilir; ekranda hazır modele dönüş yolu, günlükte sebep yazar."""
    monkeypatch.setattr(onnxruntime, "InferenceSession", oturum)
    monkeypatch.setattr(tespit, "_ort_paketleri", lambda: ["onnxruntime"])
    with pytest.raises(ModelHatasi) as hata:
        Tespitci(model, "cpu")
    assert "uyumlu değil" in hata.value.kullanici_mesaji
    assert "MODEL_DOSYASI" in hata.value.kullanici_mesaji
    assert sebep in hata.value.teknik_ayrinti


def test_forklift_modelinin_bicimi_kabul_edilir(model, monkeypatch):
    """Birleşik forklift modeli: 6 sınıf sütunu, sözlük biçiminde sınıf listesi
    (el transpaleti eşlenmez), kutular ham, puanlar 0-1 (egitim/forklift)."""
    ust_veri = {"dalsan_classes": '{"0": "person", "1": "forklift", "2": "truck", "4": "truck"}'}
    monkeypatch.setattr(
        onnxruntime, "InferenceSession", _oturum(_cikti(sinif=6), ust_veri=ust_veri)
    )
    monkeypatch.setattr(tespit, "_ort_paketleri", lambda: ["onnxruntime"])
    tespitci = Tespitci(model, "cpu")
    assert tespitci.forklift_taniyor


@pytest.mark.parametrize("ad", ["yolox_tiny.onnx", "yolox_s.onnx"])
def test_resmi_modeller_sozlesmeyi_gecer(ad):
    yol = KOK / "models" / ad
    if not yol.exists():
        pytest.skip(f"{ad} indirilmemiş (bash models/indir.sh)")
    tespitci = Tespitci(yol, "cpu")
    assert tespitci.siniflar == ("person", "truck")


# ------------------------------------------------ CPU: beklerken dönme kapalı


class _SecenekKaydedenOturum(_SahteOturum):
    secenekler = None

    def __init__(self, yol, providers, sess_options=None, **_):
        super().__init__(yol, providers)
        _SecenekKaydedenOturum.secenekler = sess_options


@pytest.mark.parametrize("is_parcacigi", [0, 2])
def test_cikarim_beklerken_islemciyi_dondurmez(model, monkeypatch, is_parcacigi):
    """ONNX Runtime iş parçacıkları varsayılan olarak her çıkarımdan sonra
    boşta döner; saniyede 6 karede bu, işlemcinin yarısını boşa yakıyordu
    (ölçüm: %115 → %58). Dönme kapalı kalmalı; iş parçacığı sınırı da
    yalnız verildiğinde uygulanır."""
    monkeypatch.setattr(onnxruntime, "InferenceSession", _SecenekKaydedenOturum)
    monkeypatch.setattr(tespit, "_ort_paketleri", lambda: ["onnxruntime"])
    Tespitci(model, "cpu", is_parcacigi=is_parcacigi)
    secenekler = _SecenekKaydedenOturum.secenekler
    assert secenekler is not None
    for anahtar in ("session.intra_op.allow_spinning", "session.inter_op.allow_spinning"):
        assert secenekler.get_session_config_entry(anahtar) == "0"
    assert secenekler.intra_op_num_threads == is_parcacigi
