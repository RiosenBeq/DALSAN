"""Forklift modeli kullanılamazsa sistem tabanındaki hazır modelle çalışır.

Eskiden internetsiz sahada seçili forklift modeli inmediğinde insan ve araç
tespiti de dururdu; kullanıcı Ayarlar'dan hazır modele kendisi dönmeliydi
(docs/ILERLEME, denetim 24.09.2026). Operatör: "Olan problemleri de çöz".
Artık süpervizör hazır modele kendiliğinden geçer, seçim değişmez ve sebep
ekranda, /saglik'ta ve olaylarda görünür.
"""

from __future__ import annotations

import dataclasses
import types
import urllib.error
from pathlib import Path

import pytest

from app import veritabani
from app.analiz import model_adi, model_indir
from app.analiz.model_indir import ModelIndirmeHatasi
from app.analiz.tespit import ModelHatasi

FORKLIFT = "nextgen_forklift_tiny_r9.onnx"
TABAN = "yolox_tiny.onnx"


@pytest.fixture
def forklift_kayitli(monkeypatch):
    """Kayıt betiğinin yazdığı gibi bir forklift modeli (scratch kaydet.py)."""
    monkeypatch.setitem(model_indir.DALSAN_MODELLERI, FORKLIFT, "forklift-r9/tiny-v3-k1.onnx")
    monkeypatch.setitem(model_indir.FORKLIFT_TABANI, FORKLIFT, TABAN)
    monkeypatch.setitem(model_indir.BILINEN_MODELLER, FORKLIFT, "0" * 64)
    monkeypatch.setitem(model_adi.GORUNEN_ADLAR, FORKLIFT, "NextGen AI Hızlı + Forklift")


def _sahte_tespitci(dosya: Path):
    return types.SimpleNamespace(
        dosya=dosya, cihaz_uyarisi="", forklift_taniyor=dosya.name == FORKLIFT
    )


def _supervizor(ayarlar, *, inmeyen=(), acilmayan=()):
    """Gerçek _tespitciyi_kur yolu; yalnız indirme ve ONNX açma taklit edilir."""
    from app.analiz.supervizor import AnalizSupervizoru

    sup = AnalizSupervizoru(ayarlar)
    hazirlanan: list[str] = []

    def hazirla(dosya: Path | None = None) -> None:
        dosya = dosya or ayarlar.model_dosyasi
        hazirlanan.append(dosya.name)
        if dosya.name in inmeyen:
            raise ModelIndirmeHatasi(
                f"{model_adi.gorunen_model_adi(dosya.name)} indirilemedi. İnternet "
                "bağlantısını kontrol edip Kontrol Panelinden yeniden başlatın.",
                f"indirme adresi: https://ornek/{dosya.name} | {urllib.error.URLError('yok')!r}",
            )

    def ac(dosya: Path):
        if dosya.name in acilmayan:
            raise ModelHatasi(f"{dosya.name} açılamadı", f"teknik: {dosya}")
        return _sahte_tespitci(dosya)

    sup._modeli_hazirla = hazirla
    sup._tespitci_ac = ac
    sup.hazirlanan = hazirlanan
    return sup


def _kur(sup, ayarlar) -> list[tuple[str, str]]:
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        sup._tespitciyi_kur(baglanti)
        return [
            (s["event_code"], s["details"] or "")
            for s in baglanti.execute("SELECT event_code, details FROM events ORDER BY id")
        ]
    finally:
        baglanti.close()


@pytest.fixture
def forklift_ayarlari(test_ayarlari, forklift_kayitli):
    return dataclasses.replace(
        test_ayarlari, model_dosyasi=test_ayarlari.kok_dizin / "models" / FORKLIFT
    )


def test_forklift_modeli_inmezse_hazir_modelle_calisir(forklift_ayarlari):
    sup = _supervizor(forklift_ayarlari, inmeyen={FORKLIFT})
    olaylar = _kur(sup, forklift_ayarlari)

    assert sup.model_durumu == "hazir"
    assert sup.tespitci.dosya.name == TABAN
    assert sup.calisan_model == forklift_ayarlari.model_dosyasi.with_name(TABAN)
    # Seçim değişmez: sonraki başlatmada forklift modeli yeniden denenir
    assert forklift_ayarlari.model_dosyasi.name == FORKLIFT
    assert sup.hazirlanan == [FORKLIFT, TABAN]
    assert "NextGen AI Hızlı + Forklift kullanılamadığı için" in sup.model_uyarisi
    assert "NextGen AI Hızlı ile çalışıyor" in sup.model_uyarisi
    assert "Sebep: NextGen AI Hızlı + Forklift indirilemedi" in sup.model_uyarisi
    assert sup.sorunlar() == ["model_yedekte"]
    assert [kod for kod, _ in olaylar] == ["MODEL_FALLBACK"]
    # Olay metninde sebep var ama adres ve dosya adı yok; ayrıntı günlüğe gider
    assert "Hızlı + Forklift kullanılamadığı için" in olaylar[0][1]
    assert ".onnx" not in olaylar[0][1] and "https://" not in olaylar[0][1]


def test_forklift_modeli_acilmazsa_da_hazir_modelle_calisir(forklift_ayarlari):
    """İnmiş ama bozuk ya da uyumsuz dosya da insan tespitini durdurmamalı."""
    sup = _supervizor(forklift_ayarlari, acilmayan={FORKLIFT})
    olaylar = _kur(sup, forklift_ayarlari)

    assert sup.model_durumu == "hazir"
    assert sup.tespitci.dosya.name == TABAN
    assert [kod for kod, _ in olaylar] == ["MODEL_FALLBACK"]


def test_hazir_model_de_yoksa_ilk_hata_soylenir(forklift_ayarlari):
    """İkisi de kullanılamazsa sebep forklift modelinin hatasıdır (genelde
    internet); sistem modelsiz kalır ve bunu eskisi gibi söyler."""
    sup = _supervizor(forklift_ayarlari, inmeyen={FORKLIFT, TABAN})
    olaylar = _kur(sup, forklift_ayarlari)

    assert sup.model_durumu == "hata"
    assert sup.tespitci is None and sup.calisan_model is None
    assert sup.tespit_hatasi.startswith("NextGen AI Hızlı + Forklift indirilemedi")
    assert sup.model_uyarisi == ""
    assert sup.sorunlar() == ["model_yuklenemedi"]
    assert [kod for kod, _ in olaylar] == ["MODEL_LOAD_FAILED"]


def test_hazir_model_hatasinda_yedege_gecilmez(test_ayarlari):
    """Hazır modelin geçilecek başka modeli yok: davranış eskisi gibi."""
    ayarlar = dataclasses.replace(
        test_ayarlari, model_dosyasi=test_ayarlari.kok_dizin / "models" / TABAN
    )
    sup = _supervizor(ayarlar, inmeyen={TABAN})
    olaylar = _kur(sup, ayarlar)

    assert sup.model_durumu == "hata"
    assert sup.hazirlanan == [TABAN]
    assert [kod for kod, _ in olaylar] == ["MODEL_LOAD_FAILED"]


def test_forklift_modeli_calisirsa_uyari_yok(forklift_ayarlari):
    sup = _supervizor(forklift_ayarlari)
    olaylar = _kur(sup, forklift_ayarlari)

    assert sup.tespitci.dosya.name == FORKLIFT
    assert sup.calisan_model == forklift_ayarlari.model_dosyasi
    assert sup.model_uyarisi == "" and sup.sorunlar() == []
    assert olaylar == []
