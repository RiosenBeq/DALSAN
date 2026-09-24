"""Yerelde eğitilen forklift modelinin kurulumu (app/egitim/forklift_kurulum.py).

Operatör, 24.09.2026: "sadece yüklesem yeter mi ekstra kod vs. bir şey yapmam
lazım mı?" Kapalı bilgisayardaki eğitimin çıkardığı iki dosya (model ve ölçümü)
Forklift sayfasından kurulur. Sınanan:

- Kapılar ürünün kendi kopyasıyla yeniden değerlendirilir ve eğitim hattının
  kopyasıyla aynıdır (esikler.json, degerlendir.py, yerel.py'nin kapı adları).
- Ölçüm başka modele aitse, taban hazır model değilse, kısa deneme modeliyse,
  forklift tanımıyorsa ya da bir kapı kaldıysa kurulmaz.
- Kurulan model Ayarlar'da seçilebilir, seçim kendiliğinden değişmez; dosyası
  kaybolursa ya da açılmazsa sistem tabanındaki hazır modelle çalışır.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
import os
import sys
import types
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import veritabani
from app.analiz import model_adi, model_indir
from app.analiz.tespit import ModelHatasi
from app.egitim import forklift_kurulum as fk
from app.uygulama import uygulama_olustur

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "egitim" / "forklift"))

import degerlendir  # egitim/forklift/degerlendir.py
import yerel  # egitim/forklift/yerel.py

KOK = Path(__file__).resolve().parents[1]
MODEL = b"onnx modeli (sahte)"
SHA = hashlib.sha256(MODEL).hexdigest()
AD = f"nextgen_forklift_tiny_yerel_{SHA[:8]}.onnx"


def _metrikler(**degisen) -> dict:
    """Bütün kapıları tam sınırında geçen metrikler."""
    metrikler = {ad.rpartition("_en_")[0]: esik for ad, esik in fk.KAPILAR.items()}
    metrikler.update(fk_ap50=0.91, fk_r_tum=0.9)
    metrikler.update(degisen)
    return metrikler


def _olcum(**degisen) -> dict:
    olcum = {
        "model_sha256": SHA,
        "resmi": "yolox_tiny.onnx",
        "resmi_sha256": model_indir.BILINEN_MODELLER["yolox_tiny.onnx"],
        "model_forklift_taniyor": True,
        "model_karti": {"calistirma_kipi": "yerel", "boy": "tiny"},
        "metrikler": _metrikler(),
        "goruntu_sayisi": 240,
        "gecti": True,
    }
    olcum.update(degisen)
    return olcum


def _bayt(olcum: dict) -> bytes:
    return json.dumps(olcum).encode("utf-8")


class _SahteTespitci:
    def __init__(self, yol: Path, *_argumanlar, forklift: bool = True, **_ayarlar) -> None:
        self.yol = yol
        self.forklift_taniyor = forklift


# ---- eğitim hattıyla aynı sözleşme ----


def test_kapilar_ve_adlari_egitim_hattiyla_ayni():
    esikler = json.loads((KOK / "egitim" / "forklift" / "esikler.json").read_text("utf-8"))
    assert fk.KAPILAR == esikler
    assert fk.METRIK_ADLARI == yerel.METRIK_ADLARI
    assert {ad.rpartition("_en_")[0] for ad in fk.KAPILAR} <= set(fk.METRIK_ADLARI)


@pytest.mark.parametrize(
    "degisen",
    [
        {},
        {"fk_r": 0.5999},
        {"fk_r": None},
        {"insan_kaybi": 0.0101},
        {"arac_kaybi": 1e-9},
        {"gecikme_orani_p90": float("nan")},
        {"video_fk_kare_orani": 0.01, "vg_r_artisi": 0.1},
        {"arac_seti_tr_fk": True},
    ],
)
def test_kapi_degerlendirmesi_olcum_betigiyle_ayni(degisen):
    metrikler = _metrikler(**degisen)
    if degisen.get("arac_seti_tr_fk") is True:
        # bool sayı değildir: ürün kaldırır (degerlendir.py hiç bool yazmaz)
        assert "arac_seti_tr_fk_en_fazla" in fk.kalan_kapilar(metrikler)
        return
    _gecti, kalan, _ = degerlendir.kapilari_degerlendir(metrikler, fk.KAPILAR)
    assert fk.kalan_kapilar(metrikler) == kalan


# ---- ölçüm denetimi ----


@pytest.mark.parametrize(
    ("olcum", "ileti"),
    [
        (b"{bozuk", "Ölçüm dosyası okunamadı"),
        (_bayt({"merhaba": 1}), "forklift ölçümü değil"),
        (_bayt(_olcum(model_sha256="0" * 64)), "bu modele ait değil"),
        (_bayt(_olcum(resmi="baska.onnx")), "hazır modellerinden biri"),
        (_bayt(_olcum(resmi_sha256="0" * 64)), "hazır modellerinden biri"),
        (_bayt(_olcum(model_karti={"calistirma_kipi": "duman"})), "kısa denemenin"),
        (_bayt(_olcum(model_karti={"calistirma_kipi": "on_deneme"})), "kısa denemenin"),
        (_bayt(_olcum(model_forklift_taniyor=False)), "tanımıyor"),
        (_bayt(_olcum(metrikler=_metrikler(fk_r=0.41))), "Forklift bulma oranı"),
        (_bayt(_olcum(metrikler=_metrikler(video_insan_kaybi=None))), "Videoda kaybolan insan"),
    ],
)
def test_gecmeyen_olcum_kurulmaz(olcum, ileti):
    with pytest.raises(fk.KurulumHatasi, match=ileti):
        fk.olcumu_denetle(olcum, SHA)


def test_gecen_olcum_adi_tabani_ve_boyu_tasir():
    aday = fk.olcumu_denetle(_bayt(_olcum()), SHA)
    assert aday.dosya_adi == AD and aday.taban == "yolox_tiny.onnx"
    s_olcumu = _olcum(
        resmi="yolox_s.onnx", resmi_sha256=model_indir.BILINEN_MODELLER["yolox_s.onnx"]
    )
    assert fk.olcumu_denetle(_bayt(s_olcumu), SHA).dosya_adi.startswith("nextgen_forklift_s_yerel_")


# ---- kurulum ----


def test_kur_denetler_tasir_ve_yinelenen_kurulumu_atlar(tmp_path):
    klasor = tmp_path / "models"
    klasor.mkdir()
    gecici = klasor / ".kurulum.part"
    gecici.write_bytes(MODEL)
    acilan = []

    def ac(yol):
        acilan.append(yol.name)
        return _SahteTespitci(yol)

    assert fk.kur(gecici, _bayt(_olcum()), klasor, ac) == (AD, True)
    assert (klasor / AD).read_bytes() == MODEL and not gecici.exists()
    assert json.loads((klasor / AD).with_suffix(".olcum.json").read_text("utf-8"))["gecti"]
    assert acilan == [".kurulum.part"], "ürünün tespit motoruyla açıldı"

    gecici.write_bytes(MODEL)
    assert fk.kur(gecici, _bayt(_olcum()), klasor, ac) == (AD, False)
    assert len(acilan) == 1, "aynı model yeniden açılmadı"


def test_forklift_tanimayan_ya_da_acilmayan_model_kurulmaz(tmp_path):
    klasor = tmp_path / "models"
    klasor.mkdir()
    gecici = klasor / ".kurulum.part"
    gecici.write_bytes(MODEL)
    with pytest.raises(fk.KurulumHatasi, match="tanımıyor"):
        fk.kur(gecici, _bayt(_olcum()), klasor, lambda y: _SahteTespitci(y, forklift=False))

    def acilmaz(_yol):
        raise ModelHatasi("açılamadı", "bozuk")

    with pytest.raises(ModelHatasi):
        fk.kur(gecici, _bayt(_olcum()), klasor, acilmaz)
    assert sorted(p.name for p in klasor.iterdir()) == [".kurulum.part"], "hiçbir şey konmadı"


# ---- ad, görünen ad ve yedek ----


def test_yerel_modelin_adi_tabani_ve_yedegi():
    assert model_adi.yerel_forklift_tabani(AD) == "yolox_tiny.onnx"
    assert model_adi.yerel_forklift_tabani("nextgen_forklift_s_yerel_0a1b2c3d.onnx") == (
        "yolox_s.onnx"
    )
    assert model_adi.yerel_forklift_tabani("yolox_tiny.onnx") is None
    assert model_adi.yerel_forklift_tabani("nextgen_forklift_tiny_yerel_zz.onnx") is None
    assert model_adi.gorunen_model_adi(AD) == (
        f"NextGen AI Hızlı + Forklift (fabrika eğitimi {SHA[:8]})"
    )
    yol = Path("/x/models") / AD
    assert model_indir.forklift_yedegi(yol) == yol.with_name("yolox_tiny.onnx")
    assert model_indir.forklift_yedegi(yol.with_name("baska.onnx")) is None


def test_kurulu_yerel_modeller_en_yenisi_sonda(tmp_path):
    klasor = tmp_path / "models"
    klasor.mkdir()
    eski = klasor / "nextgen_forklift_tiny_yerel_00000001.onnx"
    yeni = klasor / "nextgen_forklift_s_yerel_00000002.onnx"
    for yol, zaman_ in ((eski, 1_000), (yeni, 2_000)):
        yol.write_bytes(b"x")
        os.utime(yol, (zaman_, zaman_))
    (klasor / "yolox_tiny.onnx").write_bytes(b"hazir")
    (klasor / "nextgen_forklift_tiny_yerel_00000003.onnx.part").write_bytes(b"yarim")
    assert model_indir.yerel_forklift_modelleri(klasor) == {
        eski.name: "yolox_tiny.onnx",
        yeni.name: "yolox_s.onnx",
    }
    assert list(model_indir.forklift_tabanlari(klasor))[-1] == yeni.name
    assert model_indir.yerel_forklift_modelleri(tmp_path / "yok") == {}


# ---- web: Forklift sayfası ve Ayarlar ----


@pytest.fixture
def istemci_(test_ayarlari, monkeypatch):
    monkeypatch.setattr("app.web.forklift_web.Tespitci", _SahteTespitci)
    with TestClient(uygulama_olustur(test_ayarlari, analiz=False)) as istemci:
        yield istemci, test_ayarlari


def _yukle(istemci, olcum: bytes = b"", model: bytes = MODEL):
    return istemci.post(
        "/forklift/model",
        files={
            "model": ("forklift-tiny-v3-k1.onnx", model, "application/octet-stream"),
            "olcum": (
                "forklift-tiny-v3-k1.olcum.json",
                olcum or _bayt(_olcum()),
                "application/json",
            ),
        },
        follow_redirects=False,
    )


def test_sayfadan_kurulur_olay_yazar_ve_ayarlarda_secilebilir(istemci_):
    istemci, ayarlar = istemci_
    yanit = _yukle(istemci)
    assert yanit.status_code == 303 and yanit.headers["location"] == f"/forklift?kuruldu={AD}#model"
    klasor = ayarlar.kok_dizin / "models"
    assert (klasor / AD).read_bytes() == MODEL
    assert not list(klasor.glob(".kurulum-*")), "geçici dosya kalmadı"

    sayfa = istemci.get(f"/forklift?kuruldu={AD}").text
    gorunen = f"NextGen AI Hızlı + Forklift (fabrika eğitimi {SHA[:8]})"
    assert f"“{gorunen}” kuruldu" in sayfa and "Ayarlar'dan seçilebilir" in sayfa
    assert "4. Modeli kur" in sayfa and 'enctype="multipart/form-data"' in sayfa
    assert "/tmp" not in sayfa and str(klasor) not in sayfa, "ekranda yol yok"

    baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
    try:
        olaylar = [
            json.loads(s["details"])
            for s in baglanti.execute(
                "SELECT details FROM events WHERE event_code = 'FORKLIFT_MODEL_INSTALLED'"
            )
        ]
    finally:
        baglanti.close()
    assert len(olaylar) == 1 and olaylar[0]["model"] == AD

    ayar_sayfasi = istemci.get("/ayarlar").text
    assert f'value="models/{AD}"' in ayar_sayfasi and gorunen in ayar_sayfasi
    assert "“Forklift” geçen model" in ayar_sayfasi, "forkliftli modelin kural uyarısı"
    env = ayarlar.env_yolu
    assert not env.exists() or "MODEL_DOSYASI" not in env.read_text("utf-8"), (
        "kurulum seçimi değiştirmez"
    )

    kayit = istemci.post(
        "/ayarlar/kaydet", data={"MODEL_DOSYASI": f"models/{AD}"}, follow_redirects=False
    )
    assert kayit.status_code == 303
    assert f"MODEL_DOSYASI=models/{AD}" in ayarlar.env_yolu.read_text(encoding="utf-8")

    assert _yukle(istemci).headers["location"] == f"/forklift?zaten={AD}#model"


def test_sayfa_kurulmayan_modeli_sebebiyle_reddeder(istemci_):
    istemci, ayarlar = istemci_
    yanit = _yukle(istemci, _bayt(_olcum(metrikler=_metrikler(fk_r=0.3))))
    assert yanit.status_code == 400 and "Forklift bulma oranı" in yanit.json()["hata"]
    yanit = istemci.post("/forklift/model", files={}, follow_redirects=False)
    assert yanit.status_code == 400 and "İki dosyayı da seçin" in yanit.json()["hata"]
    yanit = _yukle(istemci, model=b"")
    assert yanit.status_code == 400 and "boş" in yanit.json()["hata"]
    klasor = ayarlar.kok_dizin / "models"
    assert not klasor.exists() or not list(klasor.iterdir()), "hiçbir dosya kalmadı"


def test_listede_olmayan_yerel_model_secilemez(istemci_):
    istemci, _ = istemci_
    yanit = istemci.post(
        "/ayarlar/kaydet",
        data={"MODEL_DOSYASI": "models/nextgen_forklift_tiny_yerel_0a1b2c3d.onnx"},
        follow_redirects=False,
    )
    assert yanit.status_code == 400, "kurulmamış (dosyası olmayan) model seçilemez"


def test_secili_yerel_model_yoksa_hazir_modelle_calisir(test_ayarlari):
    """Dosya silinmiş: süpervizör tabanına döner, sebep "yeniden kurun" der."""
    from app.analiz.supervizor import AnalizSupervizoru

    ayarlar = dataclasses.replace(
        test_ayarlari, model_dosyasi=test_ayarlari.kok_dizin / "models" / AD
    )
    (ayarlar.kok_dizin / "models").mkdir()
    (ayarlar.kok_dizin / "models" / "yolox_tiny.onnx").write_bytes(b"hazir")
    sup = AnalizSupervizoru(ayarlar)
    sup._tespitci_ac = lambda dosya: types.SimpleNamespace(
        dosya=dosya, cihaz_uyarisi="", forklift_taniyor=False
    )
    baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        sup._tespitciyi_kur(baglanti)
        kodlar = [s["event_code"] for s in baglanti.execute("SELECT event_code FROM events")]
    finally:
        baglanti.close()
    assert sup.model_durumu == "hazir" and sup.tespitci.dosya.name == "yolox_tiny.onnx"
    assert kodlar == ["MODEL_FALLBACK"]
    assert "dosyası bulunamadı" in sup.model_uyarisi and "yeniden kurun" in sup.model_uyarisi
    assert ".onnx" not in sup.model_uyarisi, "ekranda dosya adı yok"
