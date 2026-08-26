"""Analiz katmanı uçtan uca duman testi: sentetik video → kamera çevrimiçi →
önizleme JPEG geliyor. Gerçek kamera/model gerekmez (docs/01: video dosyası
kaynağı regresyon testi içindir).
"""

from __future__ import annotations

import time

import cv2
import numpy as np
import pytest

from app import veritabani, zaman


def _video_uret(yol, saniye: int = 30, fps: int = 10) -> None:
    yazici = cv2.VideoWriter(str(yol), cv2.VideoWriter_fourcc(*"mp4v"), fps, (320, 240))
    for i in range(saniye * fps):
        kare = np.full((240, 320, 3), 40, dtype=np.uint8)
        x = (i * 5) % 280
        cv2.rectangle(kare, (x, 100), (x + 30, 160), (0, 200, 255), -1)
        yazici.write(kare)
    yazici.release()


@pytest.fixture
def analizli_istemci(test_ayarlari, tmp_path):
    from fastapi.testclient import TestClient

    from app.uygulama import uygulama_olustur

    video = tmp_path / "test.mp4"
    _video_uret(video)

    # Kamera, süpervizör başlamadan ÖNCE eklenir ki ilk konfig yüklemesinde görülsün
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "INSERT INTO cameras (name, source_type, source_url, sample_fps, "
            "created_at, updated_at) VALUES ('Video Test', 'file', ?, 5, ?, ?)",
            (str(video), simdi, simdi),
        )
        baglanti.commit()
    finally:
        baglanti.close()

    uygulama = uygulama_olustur(test_ayarlari, analiz=True)
    with TestClient(uygulama) as istemci:
        from conftest import TEST_SIFRESI

        istemci.post("/giris", data={"sifre": TEST_SIFRESI, "sonra": "/"})
        yield istemci


def test_video_kaynagi_cevrimici_olur_ve_onizleme_gelir(analizli_istemci, test_ayarlari):
    # Süpervizör: kamera thread'i açılır, kareler akar, durum DB'ye yazılır.
    # (Tespit modeli tmp klasörde YOK — sistem tespitsiz ama çalışır durumda.)
    son_durum = ""
    for _ in range(40):  # en fazla ~20 sn
        yanit = analizli_istemci.get("/kameralar/1/onizleme.jpg")
        baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
        try:
            son_durum = baglanti.execute("SELECT status FROM cameras WHERE id = 1").fetchone()[
                "status"
            ]
        finally:
            baglanti.close()
        if yanit.status_code == 200 and son_durum == "online":
            assert yanit.headers["content-type"] == "image/jpeg"
            assert len(yanit.content) > 500  # gerçek bir JPEG
            break
        time.sleep(0.5)
    else:
        pytest.fail(f"Kamera çevrimiçi olmadı (son durum: {son_durum})")

    # Ana sayfada model durumu dürüstçe raporlanıyor (model yok → 'Yüklenemedi')
    ana = analizli_istemci.get("/").text
    assert "Yüklenemedi" in ana
