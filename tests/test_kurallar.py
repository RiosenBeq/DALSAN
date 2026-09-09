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


# --------------------------------------------------------- araç hız sınırı
#
# Dördüncü kural tipi (şema 005). Şema kısıtı yüzünden ertelenmişti;
# docs/07 #15 → docs/03 §4.


def test_hiz_kurali_bolgesiz_kaydedilir(istemci, test_ayarlari):
    """Hız kuralı bölgesiz de tanımlanabilir: tüm kamera görüşünü kapsar."""
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": kamera_id,
            "rule_type": "vehicle_speed",
            "speed_classes": ["forklift"],
            "speed_limit_mps": "2,5",  # Türkçe ondalık ayırıcı da kabul edilmeli
            "window_size": "5",
            "cooldown_s": "90",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 303

    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute("SELECT * FROM rules WHERE rule_type = 'vehicle_speed'").fetchone()
    finally:
        baglanti.close()
    assert satir is not None
    assert satir["zone_id"] is None
    assert json.loads(satir["target_classes"]) == ["forklift"]
    assert json.loads(satir["params"]) == {"speed_limit_mps": 2.5, "window_size": 5}


def test_hiz_kurali_kalibrasyonsuz_uyari_gosterir(istemci, test_ayarlari):
    """Hız zeminden ölçülür; kalibre edilmemiş kamerada kural PASİFTİR ve
    ekran bunu söylemelidir — yoksa çalışmayan kural 'aktif' görünür."""
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": kamera_id,
            "rule_type": "vehicle_speed",
            "speed_classes": ["forklift", "truck"],
            "speed_limit_mps": "2.5",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    metin = istemci.get("/kurallar").text
    assert "Araç hız sınırı" in metin
    assert "kalibrasyon bekleniyor" in metin


def test_hiz_kurali_gecersiz_esigi_reddeder(istemci, test_ayarlari):
    """Sıfır hız sınırı her duran aracı ihlal ederdi; şema reddeder."""
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari)
    yanit = istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": kamera_id,
            "rule_type": "vehicle_speed",
            "speed_classes": ["forklift"],
            "speed_limit_mps": "0",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    assert yanit.status_code == 400
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        assert baglanti.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 0
    finally:
        baglanti.close()


def test_hiz_kurali_formda_dort_tip_de_gorunur(istemci, test_ayarlari):
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari)
    metin = istemci.get(f"/kurallar/yeni?kamera={kamera_id}").text
    for tip in ("zone_intrusion", "safe_distance", "ppe_violation", "vehicle_speed"):
        assert f'value="{tip}"' in metin
    # km/sa karşılığı ekranda yazılmalı: kullanıcı m/sn'yi kafadan çeviremez
    assert "km/sa" in metin


def test_hiz_kurali_duzenleme_formu_degerleri_geri_yukler(istemci, test_ayarlari):
    kamera_id, _ = _kamera_ve_bolge(istemci, test_ayarlari)
    istemci.post(
        "/kurallar/kaydet",
        data={
            "camera_id": kamera_id,
            "rule_type": "vehicle_speed",
            "speed_classes": ["truck"],
            "speed_limit_mps": "1.4",
            "window_size": "9",
            "enabled": "1",
        },
        follow_redirects=False,
    )
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kural_id = baglanti.execute("SELECT id FROM rules").fetchone()["id"]
    finally:
        baglanti.close()
    metin = istemci.get(f"/kurallar/{kural_id}/duzenle").text
    assert 'value="1.4"' in metin
    assert 'value="9"' in metin
    # Seçili araç geri gelmeli: kaydettiği kutu boş açılırsa kullanıcı
    # düzenlemeye girip kaydettiğinde sessizce forklift'i de ekler.
    hizli_kutular = [satir for satir in metin.splitlines() if 'name="speed_classes"' in satir]
    # İki kutu vardır (forklift, tır); yalnız kaydedilen işaretli gelmeli
    satir_ciftleri = metin.split('name="speed_classes"')
    assert 'value="truck"' in satir_ciftleri[2] and "checked" in satir_ciftleri[2]
    assert 'value="forklift"' in satir_ciftleri[1] and "checked" not in satir_ciftleri[1]
    assert len(hizli_kutular) == 2
