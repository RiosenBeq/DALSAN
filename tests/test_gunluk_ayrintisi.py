"""ÇALIŞMA ZAMANI nöbetçisi: Kontrol Paneli günlüğünde teknik ayrıntı görünmez.

Neden ayrı bir dosya gerekti:

`tests/test_model_hatasi_ekranda.py` yalnızca TARAYICIYA giden HTML'i okur.
Ama kullanıcının gördüğü ikinci bir ekran daha var: Kontrol Paneli'nin
"Sistem günlüğü" penceresi. O pencere, sistemin stdout/stderr akışını olduğu
gibi basar. Web arayüzü tertemizken günlük penceresinde şunlar yazıyordu:

    Tespit modeli yüklendi: yolox_tiny.onnx (girdi 416px, cihaz: cpu, …)
    Tespit modeli indirildi: /Users/…/models/yolox_tiny.onnx

Buradaki testler o AKIŞI okur. Sızıntı hangi yoldan gelirse gelsin görürler.

İki yönlü kontrol yapılır, çünkü tek yön yetmez:
  1) EKRAN akışında yasaklı parça GEÇMEMELİ (sızıntı yok).
  2) GÜNLÜK DOSYASINDA aynı ayrıntı GEÇMELİ (destek akışı kör kalmasın).
Sadece (1) olsaydı, ayrıntıyı tamamen silmek de testi geçerdi — ve destek
ekibinin tek ipucu yok olurdu.
"""

from __future__ import annotations

import json
import re
import sys
import types
from pathlib import Path

import pytest

from app import loglama
from app.analiz.model_adi import MARKA

KOK = Path(__file__).resolve().parents[1]

# Ekrana ÇIKMAMASI gereken parçalar (küçük/büyük harf duyarsız aranır).
YASAKLI_PARCALAR = ("yolox", ".onnx", "megvii", "github.com", "models/")

# Mutlak dosya yolu izi: "/Users/…", "C:\…" gibi.
_MUTLAK_YOL = re.compile(r"(?:[A-Za-z]:\\\\?|/(?:Users|home|private|var|tmp|opt)/)")


def _satirlar(metin: str) -> list[dict]:
    """Akıştaki JSON günlük satırlarını çözer; JSON olmayan satırları atar."""
    cozulen = []
    for ham in metin.splitlines():
        ham = ham.strip()
        if not ham.startswith("{"):
            continue
        cozulen.append(json.loads(ham))
    return cozulen


def _ekran_satirlari(capsys) -> list[dict]:
    yakalanan = capsys.readouterr()
    return _satirlar(yakalanan.out + yakalanan.err)


def _dosya_satirlari(ayarlar) -> list[dict]:
    return _satirlar(ayarlar.log_dosyasi.read_text(encoding="utf-8"))


def _ekranda_sizinti_yok(satirlar: list[dict], nerede: str, *yollar: str) -> None:
    """Ekran akışının TAMAMINDA teknik iz var mı?"""
    govde = json.dumps(satirlar, ensure_ascii=False)
    dusuk = govde.lower()
    for parca in YASAKLI_PARCALAR:
        assert parca not in dusuk, f"{nerede} ekranına teknik ayrıntı sızmış: {parca!r}"
    for yol in yollar:
        assert yol not in govde, f"{nerede} ekranına dosya yolu sızmış: {yol}"
    izler = _MUTLAK_YOL.findall(govde)
    assert not izler, f"{nerede} ekranında mutlak dosya yolu var: {sorted(set(izler))}"


# ---- biçimlendiricinin kendisi ----


def test_ekran_bicimi_ayrintiyi_yazmaz_dosya_bicimi_yazar(test_ayarlari, capsys):
    """Aynı kayıt iki akışa iki farklı ayrıntı seviyesiyle yazılır."""
    loglama.kur(test_ayarlari)
    loglama.log_al("deneme").info(
        "Sistem hazır.", extra={"ayrinti": "veritabanı: /Users/biri/veri/dalsan.db"}
    )

    ekran = _ekran_satirlari(capsys)
    assert len(ekran) == 1, f"Ekrana tek satır düşmeli, düşen: {ekran}"
    assert ekran[0]["mesaj"] == "Sistem hazır."
    assert "ayrinti" not in ekran[0], "Teknik ayrıntı Kontrol Paneli penceresine düşmüş"

    dosya = _dosya_satirlari(test_ayarlari)
    assert len(dosya) == 1
    assert "dalsan.db" in dosya[0]["ayrinti"], "Ayrıntı günlük dosyasından da silinmiş"


def test_yigin_izi_ekrana_dusmez_dosyada_durur(test_ayarlari, capsys):
    """Yığın izi kaynak dosyaların mutlak yollarını içerir — ekrana değil,
    yalnızca destek ekibine giden dosyaya yazılır."""
    loglama.kur(test_ayarlari)
    try:
        raise ValueError("özgün hata metni")
    except ValueError as hata:
        loglama.log_al("deneme").error("Bir işlem tamamlanamadı.", exc_info=hata)

    ekran = _ekran_satirlari(capsys)
    assert "ayrinti" not in ekran[0]
    assert ekran[0]["mesaj"] == "Bir işlem tamamlanamadı."

    dosya = _dosya_satirlari(test_ayarlari)
    assert "ValueError" in dosya[0]["ayrinti"]
    assert "özgün hata metni" in dosya[0]["ayrinti"]


def test_bos_ayrinti_alani_uydurulmaz(test_ayarlari, capsys):
    """Ayrıntısı olmayan satır, dosyada da boş bir `ayrinti` alanı taşımaz."""
    loglama.kur(test_ayarlari)
    loglama.log_al("deneme").info("Analiz süpervizörü başladı.")

    assert "ayrinti" not in _ekran_satirlari(capsys)[0]
    assert "ayrinti" not in _dosya_satirlari(test_ayarlari)[0]


# ---- gerçek kod yolları ----


class _SahteGirdi:
    name = "images"
    shape = [1, 3, 416, 416]


class _SahteOturum:
    """onnxruntime.InferenceSession yerine geçer — gerçek model dosyası gerekmez."""

    def __init__(self, *_args, **_kwargs) -> None:
        pass

    def get_providers(self) -> list[str]:
        return ["CPUExecutionProvider"]

    def get_inputs(self) -> list[_SahteGirdi]:
        return [_SahteGirdi()]


@pytest.fixture
def sahte_onnxruntime(monkeypatch):
    """tespit.py import'u fonksiyon içinde yapar; sys.modules'a sahte koymak yeter."""
    sahte = types.ModuleType("onnxruntime")
    sahte.InferenceSession = _SahteOturum
    monkeypatch.setitem(sys.modules, "onnxruntime", sahte)
    return sahte


def test_model_yuklendi_satirinda_dosya_adi_ekranda_gorunmez(
    test_ayarlari, sahte_onnxruntime, capsys
):
    """GERÇEK başarı yolu: Tespitci kurulur, "yüklendi" satırı basılır.

    Ekranda ürün adı ve ayarlar; dosya adı ve tam yol yalnızca günlükte.
    """
    from app.analiz.tespit import Tespitci

    model = test_ayarlari.kok_dizin / "models" / "yolox_tiny.onnx"
    model.parent.mkdir(parents=True, exist_ok=True)
    model.write_bytes(b"sahte")

    loglama.kur(test_ayarlari)
    Tespitci(model, "cpu")

    ekran = _ekran_satirlari(capsys)
    assert ekran, "Model yüklendi satırı hiç basılmamış"
    _ekranda_sizinti_yok(ekran, "Model yüklendi", str(model))
    mesaj = ekran[-1]["mesaj"]
    assert mesaj.startswith(f"{MARKA} Hızlı yüklendi"), f"Ekranda ürün adı yok: {mesaj}"
    assert "416px" in mesaj, "Kullanıcıya yararlı ayar bilgisi de kaybolmamalı"
    assert "cihaz: cpu" in mesaj

    dosya = _dosya_satirlari(test_ayarlari)
    assert str(model) in dosya[-1]["ayrinti"], "Tam yol günlük dosyasından da silinmiş"


def test_model_indirme_satirlarinda_dosya_yolu_ekranda_gorunmez(test_ayarlari, monkeypatch, capsys):
    """GERÇEK indirme yolu: "indiriliyor" ve "indirildi" satırları."""
    import dataclasses

    import app.analiz.supervizor as supervizor_modulu
    from app.analiz.supervizor import AnalizSupervizoru

    model = test_ayarlari.kok_dizin / "models" / "yolox_tiny.onnx"
    ayarlar = dataclasses.replace(test_ayarlari, model_dosyasi=model)

    def sahte_indir(hedef, _ilerleme=None) -> None:
        hedef.parent.mkdir(parents=True, exist_ok=True)
        hedef.write_bytes(b"sahte")

    monkeypatch.setattr(supervizor_modulu, "modeli_indir", sahte_indir)

    loglama.kur(ayarlar)
    AnalizSupervizoru(ayarlar)._modeli_hazirla()

    ekran = _ekran_satirlari(capsys)
    assert len(ekran) >= 2, f"İndirme satırları basılmamış: {ekran}"
    _ekranda_sizinti_yok(ekran, "Model indirme", str(model))
    birlesik = " ".join(satir["mesaj"] for satir in ekran)
    assert f"{MARKA} Hızlı" in birlesik, f"Ekranda ürün adı yok: {birlesik}"

    dosya = _dosya_satirlari(ayarlar)
    assert any(str(model) in satir.get("ayrinti", "") for satir in dosya), (
        "Tam yol günlük dosyasından da silinmiş"
    )


def test_model_hatasinda_ekranda_sade_mesaj_dosyada_teknik_ayrinti(test_ayarlari, capsys):
    """GERÇEK hata yolu: model yok → süpervizör hatayı loglar.

    Ekranda kullanıcı mesajı, günlük dosyasında `teknik_ayrinti` durur.
    """
    from app import veritabani
    from app.analiz.supervizor import AnalizSupervizoru

    loglama.kur(test_ayarlari)
    supervizor = AnalizSupervizoru(test_ayarlari)
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)  # sistem olayı yazılabilsin
        supervizor._tespitciyi_kur(baglanti)
    finally:
        baglanti.close()
    assert supervizor.model_durumu == "hata", "Test kurulumu bozuk: hata dalı çalışmamış"

    ekran = _ekran_satirlari(capsys)
    _ekranda_sizinti_yok(ekran, "Model hatası", str(test_ayarlari.model_dosyasi))
    assert any(MARKA in satir["mesaj"] for satir in ekran), "Ekranda ürün adı yok"

    dosya = _dosya_satirlari(test_ayarlari)
    assert any(str(test_ayarlari.model_dosyasi) in satir.get("ayrinti", "") for satir in dosya), (
        "Tam yol günlük dosyasından da silinmiş — destek akışı kör kalır"
    )


def test_acilis_satirinda_veritabani_yolu_ekranda_gorunmez(test_ayarlari, capsys):
    """Uygulama açılışı: "Sistem hazır." satırı veritabanının tam yolunu basmaz."""
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    loglama.kur(test_ayarlari)
    with TestClient(uygulama_olustur(test_ayarlari, analiz=False)):
        pass

    ekran = _ekran_satirlari(capsys)
    _ekranda_sizinti_yok(ekran, "Açılış", str(test_ayarlari.veritabani_yolu))
    assert any(satir["mesaj"] == "Sistem hazır." for satir in ekran), (
        f"Açılış satırı basılmamış: {ekran}"
    )

    dosya = _dosya_satirlari(test_ayarlari)
    assert any(str(test_ayarlari.veritabani_yolu) in satir.get("ayrinti", "") for satir in dosya)


# ---- kaynak taraması: yeni bir sızıntı yolu açılmasın ----


def test_gunluge_ham_dosya_adi_veren_satir_yok():
    """`model_dosyasi.name` günlük metnine doğrudan yazılırsa ekranda görünür.

    İzinli tek kullanım `gorunen_model_adi(...)` içindedir.
    """
    for goreli in ("backend/app/analiz/tespit.py", "backend/app/analiz/supervizor.py"):
        kaynak = (KOK / goreli).read_text(encoding="utf-8")
        ham = re.findall(
            r"^(?!.*gorunen_model_adi).*(?:model_dosyasi|dosya)\.name.*$", kaynak, re.MULTILINE
        )
        ham = [satir for satir in ham if not satir.strip().startswith("#")]
        assert not ham, f"{goreli} ekrana ham dosya adı veriyor: {ham}"
