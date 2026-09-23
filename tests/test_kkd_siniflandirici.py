"""KKD sınıflandırıcısı: ONNX sözleşmesi, sha256 ve gözlem (docs/17 §5.2, §12.5; Faz 3c).

Gerçek bir KKD modeli yok (saha verisiyle ürün dışında eğitilecek); `onnx`
paketi de kurulu değil. Testler, ONNX Runtime oturumunun genel API'sini taklit
eden sahte bir oturumla koşar: sözleşme denetimi, sha256 ve gözlem üretimi
gerçek kod yolundan geçer.
"""

from __future__ import annotations

import hashlib
import json
from types import SimpleNamespace

import numpy as np
import pytest

from app import veritabani
from app.analiz.kkd_siniflandirici import KkdSiniflandirici
from app.analiz.supervizor import AnalizSupervizoru
from app.analiz.tespit import ModelHatasi
from app.rules.tipler import BELIRSIZ, VAR, YOK

MODEL_BAYTLARI = b"sahte-kkd-modeli"


class _Oturum:
    """onnxruntime.InferenceSession'ın kullanılan yüzü."""

    def __init__(
        self,
        cevap=None,
        girdi_bicimi=("N", 3, 256, 128),
        ciktilar=("baret", "yelek"),
        girdi_sayisi=1,
        kart=None,
    ):
        self.cevap = cevap or (lambda n: (_olasilik(n, 0.9, 0.05), _olasilik(n, 0.1, 0.8)))
        self.girdi_bicimi = list(girdi_bicimi)
        self.cikti_adlari = ciktilar
        self.girdi_sayisi = girdi_sayisi
        self.kart = kart if kart is not None else {"surum": "kkd-1", "egitim_tarihi": "2026-10"}
        self.cagrilar: list[np.ndarray] = []

    def get_inputs(self):
        return [
            SimpleNamespace(name=f"girdi{i}", shape=self.girdi_bicimi)
            for i in range(self.girdi_sayisi)
        ]

    def get_outputs(self):
        return [SimpleNamespace(name=ad) for ad in self.cikti_adlari]

    def get_modelmeta(self):
        return SimpleNamespace(custom_metadata_map=self.kart)

    def run(self, adlar, besleme):
        girdi = next(iter(besleme.values()))
        self.cagrilar.append(girdi)
        baret, yelek = self.cevap(len(girdi))
        return [{"baret": baret, "yelek": yelek}[ad] for ad in adlar]


def _olasilik(n: int, var: float, yok: float) -> np.ndarray:
    return np.tile(np.array([[var, yok, 1.0 - var - yok]], dtype=np.float32), (n, 1))


@pytest.fixture
def model(tmp_path):
    klasor = tmp_path / "models"
    klasor.mkdir()
    dosya = klasor / "kkd.onnx"
    dosya.write_bytes(MODEL_BAYTLARI)
    ozet = hashlib.sha256(MODEL_BAYTLARI).hexdigest()
    (klasor / "SHA256SUMS").write_text(
        f"427cc366d34e27ff7a03e2899b5e3671425c262ea2291f88bb942bc1cc70b0f7  yolox_tiny.onnx\n"
        f"{ozet}  kkd.onnx\n",
        encoding="utf-8",
    )
    return dosya


def _kirpik(bgr=(40, 80, 120)) -> np.ndarray:
    return np.full((256, 128, 3), bgr, dtype=np.uint8)


# ------------------------------------------------------------------ yükleme ve bütünlük


def test_dosya_yoksa_gozlem_yok(tmp_path):
    kkd = KkdSiniflandirici(tmp_path / "models" / "kkd.onnx")
    assert kkd.model_var is False
    assert kkd.degerlendir(_kirpik()) is None
    assert kkd.degerlendir_toplu([_kirpik(), _kirpik()]) == [None, None]


def test_ozet_satiri_yoksa_yuklenmez(model):
    (model.parent / "SHA256SUMS").write_text("", encoding="utf-8")
    kuruldu = []
    with pytest.raises(ModelHatasi, match="özet satırı yok"):
        KkdSiniflandirici(model, oturum_kur=lambda yol: kuruldu.append(yol) or _Oturum())
    assert kuruldu == [], "doğrulanmamış dosya ONNX Runtime'a hiç verilmemeli"


def test_ozet_tutmazsa_yuklenmez(model):
    model.write_bytes(MODEL_BAYTLARI + b"!")  # dosya değişti, satır eski
    with pytest.raises(ModelHatasi, match="özetle aynı değil") as hata:
        KkdSiniflandirici(model, oturum_kur=lambda _: _Oturum())
    assert "beklenen" in hata.value.teknik_ayrinti


def test_acilamayan_dosya_anlasilir_hata(model):
    def _bozuk(_):
        raise RuntimeError("INVALID_PROTOBUF")

    with pytest.raises(ModelHatasi, match="açılamadı"):
        KkdSiniflandirici(model, oturum_kur=_bozuk)


@pytest.mark.parametrize(
    ("oturum", "parca"),
    [
        (_Oturum(ciktilar=("helmet", "vest")), "çıktı adları"),
        (_Oturum(girdi_bicimi=("N", 3, 224, 224)), "girdi biçimi"),
        (_Oturum(girdi_sayisi=2), "2 girdi"),
        # Softmax modelin dışında kalmış: ham skorlar olasılık değildir
        (
            _Oturum(cevap=lambda n: (np.full((n, 3), 2.5, np.float32),) * 2),
            "olasılık değil",
        ),
        (_Oturum(cevap=lambda n: (np.full((n, 2), 0.5, np.float32),) * 2), "[N, 3] olmalı"),
    ],
)
def test_sozlesmeye_uymayan_model_yuklenmez(model, oturum, parca):
    with pytest.raises(ModelHatasi, match="sözleşmeye uymuyor") as hata:
        KkdSiniflandirici(model, oturum_kur=lambda _: oturum)
    assert parca in hata.value.kullanici_mesaji


# ------------------------------------------------------------------ gözlem


def test_gozlem_olasiliktan_uretilir_surum_ve_kart(model):
    kkd = KkdSiniflandirici(model, oturum_kur=lambda _: _Oturum())
    ozet = hashlib.sha256(MODEL_BAYTLARI).hexdigest()
    assert kkd.model_var is True
    assert kkd.model_surumu == f"kkd-{ozet[:12]}"
    assert kkd.kart == {"surum": "kkd-1", "egitim_tarihi": "2026-10"}

    gozlem = kkd.degerlendir(_kirpik())
    assert (gozlem.baret, gozlem.yelek) == (VAR, YOK)
    assert gozlem.baret_guven == pytest.approx(0.9)
    assert gozlem.yelek_guven == pytest.approx(0.8)
    assert gozlem.model_surumu == kkd.model_surumu
    assert gozlem.netlik == 0.0  # düz renk: hiç kenar yok


def test_gorunmuyor_belirsizdir(model):
    oturum = _Oturum(cevap=lambda n: (_olasilik(n, 0.05, 0.05), _olasilik(n, 0.1, 0.1)))
    gozlem = KkdSiniflandirici(model, oturum_kur=lambda _: oturum).degerlendir(_kirpik())
    assert (gozlem.baret, gozlem.yelek) == (BELIRSIZ, BELIRSIZ)
    assert gozlem.baret_guven == pytest.approx(0.9)


def test_dusuk_olasilik_esigi_kuralda(model):
    """Sınıflandırıcı eşik uygulamaz, olasılığı taşır: 'düşük güven belirsizdir'
    kararının tek yeri kuralın min_confidence'ıdır (rules/kkd.py)."""
    oturum = _Oturum(cevap=lambda n: (_olasilik(n, 0.3, 0.4), _olasilik(n, 0.4, 0.3)))
    gozlem = KkdSiniflandirici(model, oturum_kur=lambda _: oturum).degerlendir(_kirpik())
    assert gozlem.baret == YOK and gozlem.baret_guven == pytest.approx(0.4)


def test_girdi_rgb_ve_0_1_araliginda(model):
    oturum = _Oturum()
    kkd = KkdSiniflandirici(model, oturum_kur=lambda _: oturum)
    kkd.degerlendir(_kirpik(bgr=(255, 0, 0)))  # OpenCV BGR: saf mavi
    girdi = oturum.cagrilar[-1]
    assert girdi.shape == (1, 3, 256, 128) and girdi.dtype == np.float32
    assert girdi[0, 0].max() == 0.0 and girdi[0, 2].min() == 1.0  # R kanalı 0, B kanalı 1


@pytest.mark.parametrize(("bicim", "cagri"), [(("N", 3, 256, 128), 1), ((1, 3, 256, 128), 3)])
def test_toplu_ya_da_tek_tek(model, bicim, cagri):
    oturum = _Oturum(girdi_bicimi=bicim)
    kkd = KkdSiniflandirici(model, oturum_kur=lambda _: oturum)
    oturum.cagrilar.clear()  # yüklemedeki deneme çalıştırması sayılmaz
    gozlemler = kkd.degerlendir_toplu([_kirpik(), _kirpik(), _kirpik()])
    assert len(gozlemler) == 3 and all(g.baret == VAR for g in gozlemler)
    assert len(oturum.cagrilar) == cagri


# ------------------------------------------------------------------ süpervizör ve sayfa


def test_bozuk_model_olay_yazar_ve_modelsiz_devam_eder(test_ayarlari, model):
    import dataclasses

    model.write_bytes(b"degismis")
    ayarlar = dataclasses.replace(test_ayarlari, kkd_model_dosyasi=model)
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    try:
        supervizor = AnalizSupervizoru(ayarlar)
        supervizor._kkd_modelini_kur(baglanti)
        assert supervizor.kkd.model_var is False
        assert "özetle aynı değil" in supervizor.kkd_hatasi
        satir = baglanti.execute(
            "SELECT details FROM events WHERE event_code = 'MODEL_LOAD_FAILED'"
        ).fetchone()
        assert satir and json.loads(satir[0])["mesaj"].startswith("KKD modeli yüklenmedi")
    finally:
        baglanti.close()


def test_model_yokken_olay_yazilmaz(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    veritabani.semayi_uygula(baglanti)
    try:
        supervizor = AnalizSupervizoru(test_ayarlari)
        supervizor._kkd_modelini_kur(baglanti)
        assert supervizor.kkd.model_var is False and supervizor.kkd_hatasi is None
        assert baglanti.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0
    finally:
        baglanti.close()
