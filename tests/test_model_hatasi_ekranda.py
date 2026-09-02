"""ÇALIŞMA ZAMANI nöbetçisi: model hatası ekranında teknik ayrıntı görünmez.

Neden ayrı bir dosya gerekti (bu testlerin var oluş sebebi):

`tests/test_gorunen_model_adi.py` kaynak koddaki metin SABİTLERİNİ tarar.
Sızıntı ise sabitte değil, f-string ile ÇALIŞMA ANINDA kuruluyordu — dosya
yolu ve dosya adı koda yazılı olmadığı için tarama onları göremezdi. Yani
"sabitte 'yolox' geçmiyor" demek, "ekranda 'yolox' görünmüyor" demek DEĞİLDİR.

Buradaki testler sabite hiç bakmaz. Uygulamayı gerçekten ayağa kaldırır,
modeli bilerek eksiltir/bozar, süpervizörün GERÇEK hata yolunu çalıştırır ve
tarayıcıya giden HTML'i okur. Sızıntı hangi yoldan gelirse gelsin — f-string,
şablon, istisna metni — bu testler görür.

İki yönlü kontrol yapılır, çünkü tek yön yetmez:
  1) Yasaklı parçalar HTML'de GEÇMEMELİ (sızıntı yok).
  2) Markalı metin HTML'de GEÇMELİ (mesaj gerçekten basılmış).
Sadece (1) olsaydı, boş bir sayfa da testi geçerdi.

Teknik ayrıntı kaybolmuyor: aynı testler tam dosya yolunun günlük metninde
(`teknik_ayrinti`) DURDUĞUNU da doğrular — destek akışı oradan kopyalanıyor.
"""

from __future__ import annotations

import dataclasses
import re
from contextlib import contextmanager
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import veritabani
from app.analiz.model_adi import MARKA
from app.uygulama import uygulama_olustur

# Ekrana ÇIKMAMASI gereken parçalar (küçük/büyük harf duyarsız aranır).
# Hepsi kullanıcının hiçbir işine yaramayan, yalnızca korkutan teknik izler:
# alt bileşen adı, dosya uzantısı, kaynak deposu, kurulum betiği, kaynak
# ağacındaki klasör adı.
YASAKLI_PARCALAR = ("yolox", ".onnx", "megvii", "github.com", "indir.sh", "models/")

# Mutlak dosya yolu izi: "/Users/...", "C:\..." gibi. Ekranda gösterilen
# yollar kök klasöre GÖRE yazılır (rotalar._kokten_yol), mutlak yol çıkmaz.
_MUTLAK_YOL = re.compile(r"(?:[A-Za-z]:\\\\?|/(?:Users|home|private|var|tmp|opt)/)")


def _yasaklilari_dogrula(govde: str, nerede: str, ayarlar) -> None:
    """HTML gövdesinde teknik iz var mı? Varsa hangi parça olduğunu söyler."""
    dusuk = govde.lower()
    for parca in YASAKLI_PARCALAR:
        assert parca not in dusuk, f"{nerede} ekranına teknik ayrıntı sızmış: {parca!r}"

    # Somut kontrol: bu testin kullandığı GERÇEK mutlak yollar sayfada olmamalı.
    gercek_yollar = (
        str(ayarlar.model_dosyasi),
        str(ayarlar.model_dosyasi.parent),
        str(ayarlar.kok_dizin),
    )
    for yol in gercek_yollar:
        assert yol not in govde, f"{nerede} ekranına dosya yolu sızmış: {yol}"

    # Genel kontrol: yolun biçimi değişse de (başka işletim sistemi, başka
    # geçici klasör) mutlak yol görünümündeki hiçbir metin ekrana çıkmamalı.
    izler = _MUTLAK_YOL.findall(govde)
    assert not izler, f"{nerede} ekranında mutlak dosya yolu var: {sorted(set(izler))}"


def _model_ayarlari(temel_ayarlar, model_dosyasi: Path):
    """Aynı test ayarları, yalnızca model dosyası değiştirilmiş kopya."""
    return dataclasses.replace(temel_ayarlar, model_dosyasi=model_dosyasi)


@contextmanager
def _hatali_model_ile_ac(ayarlar):
    """Uygulamayı ayağa kaldırır, tespitçiyi GERÇEK kod yoluyla kurmayı dener.

    Süpervizör iş parçacığı başlatılmaz (kameralar açılmasın); onun yerine
    hatayı üreten adım — `_tespitciyi_kur` — doğrudan çağrılır. Böylece ekrana
    basılan metin, sahada basılacak metnin ta kendisidir; test için elle
    yazılmış bir taklidi değil.
    """
    from app.analiz.supervizor import AnalizSupervizoru

    uygulama = uygulama_olustur(ayarlar, analiz=False)
    with TestClient(uygulama) as istemci:
        supervizor = AnalizSupervizoru(ayarlar)
        baglanti = veritabani.baglanti_ac(ayarlar.veritabani_yolu)
        try:
            supervizor._tespitciyi_kur(baglanti)
        finally:
            baglanti.close()
        assert supervizor.model_durumu == "hata", (
            "Test kurulumu bozuk: model yüklenmiş, hata dalı hiç çalışmamış."
        )
        uygulama.state.supervizor = supervizor
        yield istemci, supervizor


def _hata_sayfalari(istemci) -> dict[str, str]:
    """Model hatasının kullanıcıya göründüğü sayfaların HTML gövdeleri.

    Ana sayfa "Tespit modeli" satırında mesajı basar; süpervizör aynı mesajı
    sistem olayı olarak da yazdığı için olay listesi ve olay ayrıntısı da
    kontrol edilir — sızıntı bu üç yerden herhangi birinde çıkabilir.

    Komuta ekranı da listeye eklendi: ilk kurulum kontrol listesinin ilk satırı
    aynı hata metnini gösteriyor, yani sızıntı için DÖRDÜNCÜ bir yol açıldı.
    """
    sayfalar = {}
    for yol in ("/", "/olaylar", "/komuta"):
        yanit = istemci.get(yol)
        assert yanit.status_code == 200, f"{yol} açılmadı: {yanit.status_code}"
        sayfalar[yol] = yanit.text

    son_olay = istemci.get("/olaylar/1")
    if son_olay.status_code == 200:
        sayfalar["/olaylar/1"] = son_olay.text
    return sayfalar


def _markali_dogrula(sayfalar: dict[str, str], beklenen_ad: str) -> None:
    """Mesaj gerçekten basılmış mı? (Boş sayfa testi geçmesin.)"""
    ana = sayfalar["/"]
    assert MARKA in ana, "Ana sayfada marka adı yok — hata mesajı hiç basılmamış olabilir"
    assert beklenen_ad in ana, f"Ana sayfada beklenen ürün adı yok: {beklenen_ad}"
    assert "Kontrol Paneli" in ana, "Kullanıcıya ne yapacağı söylenmemiş"

    olaylar = sayfalar["/olaylar"]
    assert MARKA in olaylar, "Olay listesinde marka adı yok — sistem olayı yazılmamış olabilir"


# ---- 1. dal: model dosyası hiç yok (kullanıcının kendi modeli) ----


def test_model_dosyasi_yokken_ekranda_teknik_ayrinti_cikmaz(test_ayarlari):
    """conftest ayarları var olmayan bir model dosyasına işaret eder.

    Dosya yok ve hazır modellerden biri de değil → süpervizör indirmeyi atlar,
    kullanıcıya markalı açıklama verir. Ekranda ne dosya yolu ne dosya adı olur.
    """
    from app.analiz.model_adi import OZEL_MODEL_ADI

    assert not test_ayarlari.model_dosyasi.exists(), "Test kurulumu: model dosyası olmamalı"

    with _hatali_model_ile_ac(test_ayarlari) as (istemci, supervizor):
        sayfalar = _hata_sayfalari(istemci)
        for yol, govde in sayfalar.items():
            _yasaklilari_dogrula(govde, yol, test_ayarlari)
        _markali_dogrula(sayfalar, OZEL_MODEL_ADI)

        # Ayrıntı kaybolmadı: tam yol destek için günlük metninde duruyor.
        assert str(test_ayarlari.model_dosyasi) not in supervizor.tespit_hatasi


# ---- 2. dal: hazır model indirilemedi, dosya ortada yok ----


def test_hazir_model_inmediyse_ekranda_teknik_ayrinti_cikmaz(test_ayarlari, monkeypatch):
    """Hazır model seçili ama dosya yerine ulaşmamış (indirme yarıda kalmış,
    disk dolmuş vb.). İndirme adımı testte ağa çıkmasın diye devre dışı
    bırakılır — mesajı üreten kod yolu bundan sonrası, tamamen gerçektir.
    """
    import app.analiz.supervizor as supervizor_modulu

    ayarlar = _model_ayarlari(test_ayarlari, test_ayarlari.kok_dizin / "models" / "yolox_tiny.onnx")

    def indirme_yok(*_args, **_kwargs) -> None:
        """Ağ yok: indirme çalıştı ama geriye dosya bırakmadı."""

    monkeypatch.setattr(supervizor_modulu, "modeli_indir", indirme_yok)

    with _hatali_model_ile_ac(ayarlar) as (istemci, supervizor):
        sayfalar = _hata_sayfalari(istemci)
        for yol, govde in sayfalar.items():
            _yasaklilari_dogrula(govde, yol, ayarlar)
        _markali_dogrula(sayfalar, f"{MARKA} Hızlı")

        assert str(ayarlar.model_dosyasi) not in supervizor.tespit_hatasi


# ---- 3. dal: model dosyası var ama bozuk ----


def test_bozuk_model_dosyasinda_ekranda_teknik_ayrinti_cikmaz(test_ayarlari):
    """Dosya yerinde ama içeriği geçerli bir model değil.

    Bu dalda hata metnini üreten kütüphanedir; özgün metin dosyanın TAM YOLUNU
    içerir. Ekrana o metin değil, sade Türkçe açıklama çıkmalı.
    """
    ayarlar = _model_ayarlari(test_ayarlari, test_ayarlari.kok_dizin / "models" / "yolox_tiny.onnx")
    ayarlar.model_dosyasi.parent.mkdir(parents=True, exist_ok=True)
    ayarlar.model_dosyasi.write_bytes(b"bu gecerli bir model dosyasi degil" * 64)

    with _hatali_model_ile_ac(ayarlar) as (istemci, supervizor):
        sayfalar = _hata_sayfalari(istemci)
        for yol, govde in sayfalar.items():
            _yasaklilari_dogrula(govde, yol, ayarlar)
        _markali_dogrula(sayfalar, f"{MARKA} Hızlı")

        assert str(ayarlar.model_dosyasi) not in supervizor.tespit_hatasi


# ---- günlük tarafı: ekrandan kalkan ayrıntı destek akışında duruyor ----


@pytest.mark.parametrize("bozuk", [False, True])
def test_tam_dosya_yolu_gunluk_metninde_duruyor(test_ayarlari, monkeypatch, bozuk):
    """Ekranda gizlenen bilgi YOK OLMAMALI: tam yol günlüğe yazılmaya devam eder.

    Aksi halde sızıntıyı kapatırken destek ekibinin tek ipucu silinmiş olurdu.
    """
    import app.analiz.supervizor as supervizor_modulu
    from app.analiz.model_indir import ModelIndirmeHatasi
    from app.analiz.tespit import ModelHatasi

    ayarlar = _model_ayarlari(test_ayarlari, test_ayarlari.kok_dizin / "models" / "yolox_tiny.onnx")
    if bozuk:
        ayarlar.model_dosyasi.parent.mkdir(parents=True, exist_ok=True)
        ayarlar.model_dosyasi.write_bytes(b"bozuk" * 512)
    else:
        monkeypatch.setattr(supervizor_modulu, "modeli_indir", lambda *a, **k: None)

    from app.analiz.tespit import Tespitci

    with pytest.raises((ModelHatasi, ModelIndirmeHatasi)) as hata:
        Tespitci(ayarlar.model_dosyasi, "cpu")

    assert str(ayarlar.model_dosyasi) in hata.value.teknik_ayrinti, (
        "Tam dosya yolu günlük metninden de silinmiş — destek akışı kör kalır"
    )
