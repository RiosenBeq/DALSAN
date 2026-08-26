"""Ortak test kurulumu.

`pythonpath = ["backend"]` ayarı (pyproject.toml) sayesinde testler
uygulamayı çalıştığı gibi `app.` paketi olarak import eder.

Testler app.main'i BİLEREK import etmez: main.py import anında gerçek .env'i
okur ve gerçek log dosyasına yazar. Testler yan etkisiz app.uygulama
fabrikasını geçici klasörler ve analiz=False ile kullanır — gerçek veri/
klasörüne dokunulmaz, kamera/tespit iş parçacığı başlamaz.
"""

from __future__ import annotations

from pathlib import Path

import pytest

TEST_SIFRESI = "cok-gizli-test-sifresi"


@pytest.fixture
def test_ayarlari(tmp_path: Path):
    """Geçici klasöre işaret eden ayarlar — gerçek veri/ klasörüne dokunulmaz."""
    from app.ayarlar import Ayarlar

    veri = tmp_path / "veri"
    (veri / "loglar").mkdir(parents=True)
    (veri / "goruntuler").mkdir()
    return Ayarlar(
        kok_dizin=tmp_path,
        yonetici_sifresi=TEST_SIFRESI,
        veri_dizini=veri,
        veritabani_yolu=veri / "dalsan.db",
        goruntu_klasoru=veri / "goruntuler",
        log_dosyasi=veri / "loglar" / "sistem.log",
        olay_saklama_gun=180,
        goruntu_saklama_gun=90,
        kkd_ham_veri_saklama_gun=30,
        sistem_olay_saklama_gun=90,
        kkd_ornek_saat_limit=60,
        disk_uyari_gb=5,
        cikarim_cihazi="cpu",
        kare_ornekleme_fps=6,
        anons="null",
        anons_http_adresi="",
        anons_bekleme_sn=30,
        model_dosyasi=tmp_path / "models" / "olmayan-model.onnx",
    )


@pytest.fixture
def ham_istemci(test_ayarlari):
    """Oturum AÇILMAMIŞ istemci — giriş zorunluluğu testleri için."""
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    uygulama = uygulama_olustur(test_ayarlari, analiz=False)
    with TestClient(uygulama) as istemci:
        yield istemci


@pytest.fixture
def istemci(ham_istemci):
    """Oturum açılmış istemci (çerez TestClient içinde taşınır)."""
    yanit = ham_istemci.post(
        "/giris", data={"sifre": TEST_SIFRESI, "sonra": "/"}, follow_redirects=False
    )
    assert yanit.status_code == 303, "test girişi başarısız — giriş akışı bozulmuş"
    return ham_istemci
