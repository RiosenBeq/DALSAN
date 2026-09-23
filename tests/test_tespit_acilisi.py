"""Tespit modeli açılışı: GPU sağlayıcısı hatası ≠ bozuk dosya (docs/17 §13, 2a).

Eskiden `InferenceSession` her hatada "dosyası bozuk" deniyordu. CUDA seçiliyken
sürücü uyumsuzluğu da oturumu düşürür; kullanıcı sağlam bir dosyayı
değiştirmeye uğraşırken asıl sorun sürücüde kalırdı. Oturum sahtedir: testler
gerçek model dosyasına (depoda yok) ve GPU'ya bağlı değildir.
"""

from __future__ import annotations

import hashlib
from types import SimpleNamespace

import onnxruntime
import pytest

from app.analiz import model_indir, tespit
from app.analiz.tespit import ModelHatasi, Tespitci


class _SahteOturum:
    """CUDA istenirse çöker (sürücü yok), yalnız CPU ile açılır."""

    def __init__(self, yol, providers, **_):
        if "CUDAExecutionProvider" in providers:
            raise RuntimeError("CUDA sağlayıcısı başlatılamadı: libcudnn.so.9 bulunamadı")
        self._saglayicilar = list(providers)

    def get_providers(self):
        return self._saglayicilar

    def get_inputs(self):
        return [SimpleNamespace(name="images", shape=[1, 3, 416, 416])]


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
