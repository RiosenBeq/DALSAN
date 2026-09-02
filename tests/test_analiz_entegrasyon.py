"""Analiz katmanı uçtan uca duman testi: sentetik video → kamera çevrimiçi →
önizleme JPEG geliyor. Gerçek kamera/model gerekmez (docs/01: video dosyası
kaynağı regresyon testi içindir).
"""

from __future__ import annotations

import json
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


def test_yeni_kamera_cevrimdisi_olayi_uretmez(analizli_istemci, test_ayarlari):
    """Kamera eklenir eklenmez 'Kamera çevrimdışı' olayı düşmemeli (ilk bağlantı
    süresi 'bağlanıyor' sayılır); durum satırı da bunu söylemeli."""
    for _ in range(40):
        veri = analizli_istemci.get("/kameralar/1/durum.json").json()
        if veri["durum"] == "online":
            break
        assert veri["durum"] == "connecting", veri
        time.sleep(0.5)
    else:
        pytest.fail(f"Kamera çevrimiçi olmadı: {veri}")
    assert "Görüntü akıyor" in veri["mesaj"]

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        olaylar = [
            json.loads(s["details"])["mesaj"]
            for s in baglanti.execute("SELECT details FROM events WHERE event_type = 'system'")
        ]
    finally:
        baglanti.close()
    assert not any("çevrimdışı" in m for m in olaylar), olaylar
