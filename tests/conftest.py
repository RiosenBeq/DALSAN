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


@pytest.fixture
def test_ayarlari(tmp_path: Path):
    """Geçici klasöre işaret eden ayarlar — gerçek veri/ klasörüne dokunulmaz."""
    from app.ayarlar import Ayarlar

    veri = tmp_path / "veri"
    (veri / "loglar").mkdir(parents=True)
    (veri / "goruntuler").mkdir()
    # Nesne kütüphanesi klasörü GÖRÜNTÜ KLASÖRÜNÜN DIŞINDA: bakım döngüsü
    # oraya dokunmamalı (tests/test_nesne_kutuphanesi.py bunu sınar).
    (veri / "nesneler" / "taramalar").mkdir(parents=True)
    return Ayarlar(
        kok_dizin=tmp_path,
        veri_dizini=veri,
        veritabani_yolu=veri / "dalsan.db",
        goruntu_klasoru=veri / "goruntuler",
        nesne_klasoru=veri / "nesneler",
        nesne_tarama_klasoru=veri / "nesneler" / "taramalar",
        log_dosyasi=veri / "loglar" / "sistem.log",
        olay_saklama_gun=180,
        goruntu_saklama_gun=90,
        kkd_ham_veri_saklama_gun=30,
        sistem_olay_saklama_gun=90,
        kkd_ornek_saat_limit=60,
        disk_uyari_gb=5,
        cikarim_cihazi="cpu",
        kare_ornekleme_fps=6,
        fps_uyari_orani=0.6,
        tespit_guven_esigi=0.35,
        tespit_insan_guven_esigi=0.28,
        tespit_nms_esigi=0.45,
        tespit_en_kucuk_kenar_px=12,
        goruntu_iyilestirme="kapali",
        anons="null",
        anons_http_adresi="",
        anons_bekleme_sn=30,
        model_dosyasi=tmp_path / "models" / "olmayan-model.onnx",
        nesne_izinli_uzantilar=(".jpg", ".jpeg", ".png", ".webp", ".bmp"),
        nesne_foto_en_buyuk_mb=12,
        nesne_tarama_en_cok_dosya=6,
        nesne_eslesme_esigi=0.42,
        env_yolu=tmp_path / ".env",
    )


@pytest.fixture
def istemci(test_ayarlari):
    """Analizsiz (kamera iş parçacığı başlamayan) web istemcisi."""
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    uygulama = uygulama_olustur(test_ayarlari, analiz=False)
    with TestClient(uygulama) as istemci:
        yield istemci
