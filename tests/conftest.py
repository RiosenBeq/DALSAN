"""Ortak test kurulumu.

`pythonpath = ["backend"]` ayarı (pyproject.toml) sayesinde testler
uygulamayı çalıştığı gibi `app.` paketi olarak import eder.

Testler app.main'i BİLEREK import etmez: main.py import anında gerçek .env'i
okur ve gerçek log dosyasına yazar. Testler yan etkisiz app.uygulama
fabrikasını geçici klasörlerle kullanır — gerçek veri/ klasörüne dokunulmaz.
"""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def test_ayarlari(tmp_path: Path):
    """Geçici klasöre işaret eden ayarlar — gerçek veri/ klasörüne dokunulmaz."""
    from app.ayarlar import Ayarlar

    veri = tmp_path / "veri"
    (veri / "loglar").mkdir(parents=True)
    (veri / "goruntuler").mkdir()
    return Ayarlar(
        kok_dizin=tmp_path,
        yonetici_sifresi="cok-gizli-test-sifresi",
        veri_dizini=veri,
        veritabani_yolu=veri / "dalsan.db",
        goruntu_klasoru=veri / "goruntuler",
        log_dosyasi=veri / "loglar" / "sistem.log",
        olay_saklama_gun=180,
        goruntu_saklama_gun=90,
        kkd_ham_veri_saklama_gun=30,
        cikarim_cihazi="cpu",
        kare_ornekleme_fps=6,
        anons="null",
        anons_http_adresi="",
    )


@pytest.fixture
def istemci(test_ayarlari):
    """Geçici veritabanıyla çalışan test istemcisi (şema açılışta uygulanır)."""
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    uygulama = uygulama_olustur(test_ayarlari)
    with TestClient(uygulama) as istemci:
        yield istemci
