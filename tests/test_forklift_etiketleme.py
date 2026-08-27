"""Forklift etiketleme sayfası testleri (docs/08 R1)."""

from __future__ import annotations

from app import veritabani, zaman


def _ornek_olustur(test_ayarlari, bbox: str = "[0.1, 0.2, 0.5, 0.8]") -> int:
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        kare = test_ayarlari.goruntu_klasoru / "forklift-ornekler" / "kare.jpg"
        kare.parent.mkdir(parents=True, exist_ok=True)
        kare.write_bytes(b"sahte-jpeg")
        imlec = baglanti.execute(
            "INSERT INTO forklift_samples (captured_at, frame_path, bbox, source) "
            "VALUES (?, 'forklift-ornekler/kare.jpg', ?, 'auto')",
            (zaman.simdi_utc(), bbox),
        )
        baglanti.commit()
        return imlec.lastrowid
    finally:
        baglanti.close()


def test_etiketleme_akisi(istemci, test_ayarlari):
    ornek_id = _ornek_olustur(test_ayarlari)
    sayfa = istemci.get("/forklift").text
    assert "Etiketlenecek kareler" in sayfa
    assert f"ornek-{ornek_id}" in sayfa
    # Aday araç kutusu, normalize bbox'tan yüzdeye çevrilerek çizilir
    assert "left:10.0%" in sayfa
    assert "width:40.0%" in sayfa

    # Tek etiket yeter — kare etiketlenmiş sayılır ve listeden düşer
    yanit = istemci.post(f"/forklift/{ornek_id}/etiket", data={"deger": "yes"})
    assert yanit.status_code == 204
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        satir = baglanti.execute(
            "SELECT * FROM forklift_samples WHERE id = ?", (ornek_id,)
        ).fetchone()
        assert satir["label"] == "yes"
        assert satir["labeled_at"] is not None
    finally:
        baglanti.close()

    sayfa = istemci.get("/forklift").text
    assert f"ornek-{ornek_id}" not in sayfa


def test_gecersiz_etiket_reddedilir(istemci, test_ayarlari):
    ornek_id = _ornek_olustur(test_ayarlari)
    yanit = istemci.post(f"/forklift/{ornek_id}/etiket", data={"deger": "belki"})
    assert yanit.status_code == 400


def test_olmayan_ornek_404(istemci, test_ayarlari):
    _ornek_olustur(test_ayarlari)  # şema kurulsun
    yanit = istemci.post("/forklift/99999/etiket", data={"deger": "yes"})
    assert yanit.status_code == 404


def test_bozuk_bbox_sayfayi_bozmaz(istemci, test_ayarlari):
    ornek_id = _ornek_olustur(test_ayarlari, bbox="bozuk-json")
    sayfa = istemci.get("/forklift")
    assert sayfa.status_code == 200
    assert f"ornek-{ornek_id}" in sayfa.text
    assert "aday-kutu" not in sayfa.text  # kutu çizilmez, kart yine gösterilir


def test_ornek_goruntusu_servis_edilir(istemci, test_ayarlari):
    ornek_id = _ornek_olustur(test_ayarlari)
    yanit = istemci.get(f"/forklift/ornek/{ornek_id}.jpg")
    assert yanit.status_code == 200
    assert yanit.content == b"sahte-jpeg"


def test_sayac_ve_hedef_gosterilir(istemci, test_ayarlari):
    _ornek_olustur(test_ayarlari)
    sayfa = istemci.get("/forklift").text
    assert "300" in sayfa and "800" in sayfa  # docs/08 R1 hedefi
