"""Kural yönetimi testleri: form → params doğrulama → veritabanı."""

from __future__ import annotations

import json

from app import veritabani


def _kamera_ve_bolge(istemci, test_ayarlari) -> tuple[int, int]:
    video = test_ayarlari.kok_dizin / "video.mp4"
    video.write_bytes(b"sahte")  # form, dosyanın varlığını denetler
    yanit = istemci.post(
        "/kameralar/yeni",
        data={
            "name": "K1",
            "source_type": "file",
            "source_url": str(video),
            "sample_fps": "6",
        },
        follow_redirects=False,
    )
    kamera_id = int(yanit.headers["location"].rsplit("/", 1)[1])
    istemci.post(
        f"/kameralar/{kamera_id}/bolgeler",
        data={
            "name": "Rampa",
            "zone_type": "loading_area",
            "polygon": "[[0.1,0.1],[0.9,0.1],[0.9,0.9]]",
        },
        follow_redirects=False,
    )
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        bolge_id = baglanti.execute("SELECT id FROM zones").fetchone()["id"]
    finally:
        baglanti.close()
    return kamera_id, bolge_id


def test_bolge_ihlali_kurali_kaydedilir(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": kamera_id,
            "rule_type": "zone_intrusion",
            "zone_id": bolge_id,
            "target_classes": ["person"],
            "mode": "inside",
            "min_dwell_s": "2",
            "cooldown_s": "120",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute("SELECT * FROM rules").fetchone()
    finally:
        baglanti.close()
    assert satir["rule_type"] == "zone_intrusion"
    params = json.loads(satir["params"])
    assert params["mode"] == "inside"
    assert params["min_dwell_s"] == 2.0
    assert "aktif" in istemci.get("/kurallar").text


def test_bolgesiz_bolge_kurali_reddedilir(istemci, test_ayarlari):
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": kamera_id,
            "rule_type": "zone_intrusion",
            "target_classes": ["person"],
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    assert "bölgesiz" in yanit.json()["hata"]


def test_gecersiz_parametre_veritabanina_girmez(istemci, test_ayarlari):
    kamera_id, bolge_id = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": kamera_id,
            "rule_type": "ppe_violation",
            "zone_id": bolge_id,
            "required_ppe": ["helmet"],
            "violation_ratio": "0.2",  # şema en az 0.5 ister
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        adet = baglanti.execute("SELECT COUNT(*) FROM rules").fetchone()[0]
    finally:
        baglanti.close()
    assert adet == 0


def test_mesafe_kurali_kalibrasyonsuz_uyari_gosterir(istemci, test_ayarlari):
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": kamera_id,
            "rule_type": "safe_distance",
            "object_classes": ["forklift", "truck"],
            "distance_m": "3",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert "kalibrasyon bekleniyor" in istemci.get("/kurallar").text
