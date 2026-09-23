"""Komuta ekranlarında canlı uyarı, sistem şeridi ve ses çipi (docs/17 §11; Faz 2d-4).

Eskiden ihlal bandı yalnız Olaylar ve Ana Sayfa'da çıkıyordu: operatörün
başında durduğu komuta ekranları uyarı betiklerini hiç yüklemiyordu. Artık:

- bütün komuta ekranları `uyari.js` + `canli.js` + `sistem_seridi.js` yükler;
- sistem şeridinin sorun metinleri sunucudan gelir (tek kaynak);
- ekran sesinin çalışmadığı durumlar boş `catch` ile yutulmaz, çipte görünür (R41).

JS davranışı tarayıcıda doğrulanır (proje Node kullanmaz); buradaki testler
yükleme ve sözleşmeyi kilitler.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from app.web.ortak import SAGLIK_SORUN_METINLERI
from app.web.rotalar import HAZIRLIGI_BOZAN_SORUNLAR

STATIK = Path(__file__).resolve().parents[1] / "backend" / "app" / "web" / "static"

KOMUTA_EKRANLARI = (
    "/komuta",
    "/komuta/duvar",
    "/komuta/inceleme",
    "/komuta/saglik",
    "/komuta/uyari",
    "/komuta/rapor",
    "/komuta/anons",
    "/komuta/kilavuz",
)


@pytest.mark.parametrize("yol", KOMUTA_EKRANLARI)
def test_komuta_ekrani_canli_uyari_ve_seridi_yukler(istemci, yol):
    metin = istemci.get(yol).text
    for betik in ("uyari.js", "canli.js", "sistem_seridi.js"):
        assert f'src="/static/{betik}?v=' in metin, (yol, betik)
        assert metin.count(f"/static/{betik}") == 1, f"{betik} iki kez yüklenmemeli ({yol})"
    assert 'id="sistem-seridi"' in metin and 'id="canli-durum"' in metin


def test_serit_metinleri_sunucudan_gelir(istemci):
    metin = istemci.get("/komuta").text
    oznitelik = re.search(r"data-metinler='([^']*)'", metin)
    assert oznitelik, "şerit metinleri sayfada yok"
    assert json.loads(oznitelik.group(1)) == SAGLIK_SORUN_METINLERI


def test_hazirligi_bozan_her_sorunun_serit_metni_var():
    assert HAZIRLIGI_BOZAN_SORUNLAR | {"kritik_kural_pasif"} <= set(SAGLIK_SORUN_METINLERI)
    assert SAGLIK_SORUN_METINLERI["model_yuklenemedi"] == "Analiz yapılmıyor - model yüklenemedi"


def _islev_govdesi(kaynak: str, ad: str) -> str:
    """`function ad(...) {` ile başlayıp iki boşluk girintili `}` ile biten gövde."""
    baslangic = kaynak.index(f"function {ad}(")
    return kaynak[baslangic : kaynak.index("\n  }\n", baslangic)]


@pytest.mark.parametrize(
    ("islev", "degisken"), [("sesCal", "sesHatasi"), ("seslendir", "okumaHatasi")]
)
def test_ses_hatasi_bos_catch_ile_yutulmaz(islev, degisken):
    govde = _islev_govdesi((STATIK / "uyari.js").read_text(encoding="utf-8"), islev)
    yakalamalar = re.findall(r"catch \(e\) \{(.*?)\n    \}", govde, re.S)
    assert yakalamalar, f"{islev} içinde catch yok"
    for yakalama in yakalamalar:
        assert f"{degisken} =" in yakalama, f"{islev}: hata ekrana taşınmıyor"
    assert "cipiGuncelle()" in govde


def test_ses_cipinin_uc_durumu_da_yazili():
    kaynak = (STATIK / "uyari.js").read_text(encoding="utf-8")
    for parca in (
        "sesli uyarı KAPALI - açmak için tıklayın",
        "Sesli uyarı çalışmıyor",
        "Sesli uyarı beklemede - etkinleştirmek için tıklayın",
    ):
        assert parca in kaynak


def test_sistem_olayi_ayri_bantta_ihlal_bandini_ezmez():
    kaynak = (STATIK / "uyari.js").read_text(encoding="utf-8")
    duyur = kaynak[kaynak.index("duyur: function (veri)") :]
    # Sistem olayı ihlal bandına (goster) hiç girmeden döner
    assert duyur.index('veri.tip === "system"') < duyur.index("goster(veri)")
    assert "sistemGoster(veri)" in duyur


def test_canli_akis_cipi_etkinlestirir_ve_rozet_tabani_sayfadan():
    kaynak = (STATIK / "canli.js").read_text(encoding="utf-8")
    assert "cipiEtkinlestir()" in kaynak
    assert 'getAttribute("data-taban")' in kaynak
