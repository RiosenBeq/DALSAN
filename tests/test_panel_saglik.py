"""Kontrol Paneli sağlık satırı ve uvicorn günlüğü (docs/17 §9.1, §9.4; Faz 2d-3).

- Panel, portun bu sisteme ait olduğunu yine `durum: "calisiyor"` ile anlar
  (`bizim_sunucumuz_mu` bozulmaz); hazır olmayan sistem de "bizim"dir.
- Yeni "Analiz" satırı: hazır değilse kırmızı, model yüklenirken gri,
  yapılandırma eksiğinde sarı, sesli uyarı doğrulanamıyorsa gri.
- uvicorn'un günlükleri aynı JSON biçiminde dosyaya düşer; erişim
  günlüğünden başarılı GET'ler elenir.
"""

from __future__ import annotations

import importlib.util
import io
import json
import logging
from pathlib import Path

import pytest

from app import loglama

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def panel():
    tanim = importlib.util.spec_from_file_location(
        "panel_saglik", KOK / "masaustu" / "dalsan_launcher.py"
    )
    modul = importlib.util.module_from_spec(tanim)
    tanim.loader.exec_module(modul)
    return modul


# ------------------------------------------------------------------ Analiz satırı


@pytest.mark.parametrize(
    ("govde", "renk", "parca"),
    [
        (None, "gri", "-"),
        ({"durum": "calisiyor", "analiz": True, "model": "hazir", "hazir": True}, "ok", "Hazır"),
        (
            {"analiz": True, "model": "hazir", "hazir": True, "sorunlar": ["kritik_kural_pasif"]},
            "uyari",
            "kalibrasyon bekliyor",
        ),
        (
            {"analiz": True, "model": "hata", "hazir": False, "sorunlar": ["model_yuklenemedi"]},
            "hata",
            "Tespit modeli yüklenemedi",
        ),
        (
            {"analiz": True, "model": "hazir", "hazir": False, "sorunlar": ["analiz_takildi"]},
            "hata",
            "Analiz takıldı",
        ),
        ({"analiz": True, "model": "yukleniyor", "hazir": False}, "gri", "Hazırlanıyor"),
        ({"analiz": False, "model": "kapali", "hazir": False}, "hata", "Analiz çalışmıyor"),
        # Faz 4'ün alanı: sesli uyarı kanalları
        (
            {"analiz": True, "model": "hazir", "hazir": True, "uyari_garantisi": False},
            "hata",
            "hiçbir kanala ulaşmıyor",
        ),
        (
            {"analiz": True, "model": "hazir", "hazir": True, "uyari_garantisi": None},
            "gri",
            "doğrulanamıyor",
        ),
        # Tanınmayan kod uydurulmaz, olduğu gibi yazılır
        (
            {"analiz": True, "model": "hazir", "hazir": True, "sorunlar": ["yeni_kod"]},
            "uyari",
            "yeni_kod",
        ),
    ],
)
def test_analiz_satiri(panel, govde, renk, parca):
    metin, bulunan_renk = panel.analiz_satiri(govde)
    assert bulunan_renk == renk
    assert parca in metin


def test_her_saglik_kodunun_panel_metni_var(panel):
    """docs/06 §2 tablosundaki kodların hepsi panelde Türkçe yazılır."""
    from app.web.rotalar import HAZIRLIGI_BOZAN_SORUNLAR

    kodlar = HAZIRLIGI_BOZAN_SORUNLAR | {"kritik_kural_pasif", "ort_paket_cakismasi"}
    assert kodlar <= set(panel.SAGLIK_SORUN_METINLERI)


# ------------------------------------------------------------------ bizim sunucumuz mu


def test_hazir_olmayan_sistem_de_bizim_sunucumuz(panel, monkeypatch):
    govde = {"durum": "calisiyor", "analiz": True, "model": "hata", "hazir": False}
    monkeypatch.setattr(panel, "sunucu_ayakta", lambda: True)
    monkeypatch.setattr(panel, "saglik_govdesi", lambda: govde)
    assert panel.sunucu_durumu_ve_saglik() == (panel.CALISIYOR, govde)
    assert panel.sunucu_durumu() == panel.CALISIYOR
    assert panel.bizim_sunucumuz_mu() is True


def test_baskasinin_sunucusu_ve_duran_sistem(panel, monkeypatch):
    monkeypatch.setattr(panel, "sunucu_ayakta", lambda: True)
    monkeypatch.setattr(panel, "saglik_govdesi", lambda: None)
    assert panel.sunucu_durumu_ve_saglik() == (panel.BASKASINDA, None)
    monkeypatch.setattr(panel, "sunucu_ayakta", lambda: False)
    assert panel.sunucu_durumu_ve_saglik() == (panel.DURDU, None)


class _Yanit(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *hata):
        return False


@pytest.mark.parametrize(
    ("ham", "beklenen"),
    [
        (b'{"durum": "calisiyor", "hazir": true}', {"durum": "calisiyor", "hazir": True}),
        (b'["calisiyor"]', None),  # sözlük değil: eskiden AttributeError fırlatırdı
        (b"<html>baska program</html>", None),
    ],
)
def test_saglik_govdesi_bozuk_cevaba_dayanikli(panel, monkeypatch, ham, beklenen):
    monkeypatch.setattr(panel.urllib.request, "urlopen", lambda *a, **k: _Yanit(ham))
    assert panel.saglik_govdesi() == beklenen


# ------------------------------------------------------------------ uvicorn günlüğü


def _erisim(yontem: str, yol: str, durum: int) -> None:
    logging.getLogger("uvicorn.access").info(
        '%s - "%s %s HTTP/%s" %d', "127.0.0.1:50000", yontem, yol, "1.1", durum
    )


def test_uvicorn_satirlari_json_ve_basarili_get_elenir(test_ayarlari):
    loglama.kur(test_ayarlari)
    logging.getLogger("uvicorn.error").info("Started server process [%d]", 4242)
    _erisim("GET", "/saglik", 200)
    _erisim("POST", "/kurallar/kaydet", 303)
    _erisim("GET", "/kameralar/99", 500)
    loglama.kur(test_ayarlari)  # ikinci kurulum satırları ikilemez
    _erisim("DELETE", "/x", 204)

    satirlar = [
        json.loads(satir)
        for satir in test_ayarlari.log_dosyasi.read_text(encoding="utf-8").splitlines()
        if satir.strip()
    ]
    uvicorn = [s for s in satirlar if s["bilesen"].startswith("uvicorn")]
    assert [s["bilesen"] for s in uvicorn] == [
        "uvicorn.error",
        "uvicorn.access",
        "uvicorn.access",
        "uvicorn.access",
    ]
    assert uvicorn[0]["mesaj"] == "Started server process [4242]"
    mesajlar = [s["mesaj"] for s in uvicorn[1:]]
    assert '"POST /kurallar/kaydet HTTP/1.1" 303' in mesajlar[0]
    assert '"GET /kameralar/99 HTTP/1.1" 500' in mesajlar[1]
    assert '"DELETE /x HTTP/1.1" 204' in mesajlar[2]
    assert not any("/saglik" in m for m in mesajlar), "başarılı yoklama yazılmaz"
