"""KKD etiketleme sayfası testleri."""

from __future__ import annotations

from app import veritabani, zaman


def _ornek_olustur(test_ayarlari) -> int:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        crop = test_ayarlari.goruntu_klasoru / "kkd-ornekler" / "ornek.jpg"
        crop.parent.mkdir(parents=True, exist_ok=True)
        crop.write_bytes(b"sahte-jpeg")
        imlec = baglanti.execute(
            "INSERT INTO ppe_samples (captured_at, crop_path, source) "
            "VALUES (?, 'kkd-ornekler/ornek.jpg', 'auto')",
            (zaman.simdi_utc(),),
        )
        baglanti.commit()
        return imlec.lastrowid
    finally:
        baglanti.close()


def test_etiketleme_akisi(istemci, test_ayarlari):
    ornek_id = _ornek_olustur(test_ayarlari)
    sayfa = istemci.get("/kkd").text
    assert "Etiketlenecek örnekler" in sayfa
    assert f"ornek-{ornek_id}" in sayfa

    # Tek etiket → henüz 'etiketlendi' değil
    yanit = istemci.post(f"/kkd/{ornek_id}/etiket", data={"alan": "helmet", "deger": "no"})
    assert yanit.status_code == 204
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute("SELECT * FROM ppe_samples WHERE id = ?", (ornek_id,)).fetchone()
        assert satir["helmet_label"] == "no"
        assert satir["labeled_at"] is None

        # İkinci etiket → örnek etiketlenmiş sayılır
        istemci.post(f"/kkd/{ornek_id}/etiket", data={"alan": "vest", "deger": "unknown"})
        satir = baglanti.execute("SELECT * FROM ppe_samples WHERE id = ?", (ornek_id,)).fetchone()
        assert satir["vest_label"] == "unknown"
        assert satir["labeled_at"] is not None
    finally:
        baglanti.close()


def test_gecersiz_etiket_reddedilir(istemci, test_ayarlari):
    ornek_id = _ornek_olustur(test_ayarlari)
    yanit = istemci.post(f"/kkd/{ornek_id}/etiket", data={"alan": "helmet", "deger": "belki"})
    assert yanit.status_code == 400


def test_ornek_goruntusu_servis_edilir(istemci, test_ayarlari):
    ornek_id = _ornek_olustur(test_ayarlari)
    yanit = istemci.get(f"/kkd/ornek/{ornek_id}.jpg")
    assert yanit.status_code == 200
    assert yanit.content == b"sahte-jpeg"
