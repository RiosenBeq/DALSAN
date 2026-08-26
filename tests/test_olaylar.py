"""Olay kaydı ve olay ekranı testleri."""

from __future__ import annotations

import json

from app import veritabani
from app.olaylar.yazici import ihlal_yaz, sistem_olayi_yaz
from app.rules.tipler import Ihlal


def _ornek_ihlal(kamera_id: int, kural_id: int) -> Ihlal:
    return Ihlal(
        kural_id=kural_id,
        kamera_id=kamera_id,
        takip_idler=[5],
        bolge_id=None,
        olculen=2.4,
        detaylar={"sinif": "person", "kalis_s": 2.4},
    )


def _kamera_olustur(baglanti) -> int:
    from app import zaman

    simdi = zaman.simdi_utc()
    imlec = baglanti.execute(
        "INSERT INTO cameras (name, source_type, source_url, created_at, updated_at) "
        "VALUES ('K1', 'file', 'v.mp4', ?, ?)",
        (simdi, simdi),
    )
    baglanti.commit()
    return imlec.lastrowid


def test_ihlal_once_fotograf_sonra_kayit(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        kamera_id = _kamera_olustur(baglanti)
        olay_id = ihlal_yaz(
            baglanti,
            test_ayarlari,
            _ornek_ihlal(kamera_id, kural_id=1),
            kural_kaydi={"rule_type": "zone_intrusion", "id": 1},
            kanit_jpeg=b"sahte-jpeg-verisi",
        )
        satir = baglanti.execute("SELECT * FROM events WHERE id = ?", (olay_id,)).fetchone()
        assert satir["event_type"] == "violation"
        assert satir["status"] == "new"
        # Fotoğraf gerçekten diske yazılmış ve yol kayıtla eşleşiyor
        foto = test_ayarlari.goruntu_klasoru / satir["snapshot_path"]
        assert foto.read_bytes() == b"sahte-jpeg-verisi"
        detaylar = json.loads(satir["details"])
        assert detaylar["takip_idler"] == [5]
    finally:
        baglanti.close()


def test_fotografsiz_ihlal_yine_de_kaydedilir(test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        kamera_id = _kamera_olustur(baglanti)
        olay_id = ihlal_yaz(
            baglanti, test_ayarlari, _ornek_ihlal(kamera_id, 1), {"id": 1}, kanit_jpeg=None
        )
        satir = baglanti.execute("SELECT * FROM events WHERE id = ?", (olay_id,)).fetchone()
        assert satir["snapshot_path"] is None  # olay kaybolmadı
    finally:
        baglanti.close()


def test_olay_listesi_ve_durum_isaretleme(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera_id = _kamera_olustur(baglanti)
        olay_id = ihlal_yaz(
            baglanti,
            test_ayarlari,
            _ornek_ihlal(kamera_id, 1),
            {"rule_type": "zone_intrusion"},
            None,
        )
        sistem_olayi_yaz(baglanti, "Kamera çevrimdışı: K1", kamera_id=kamera_id)
    finally:
        baglanti.close()

    liste = istemci.get("/olaylar").text
    assert "Bölge ihlali" in liste
    assert "Kamera çevrimdışı: K1" in liste

    # Yanlış alarm işaretle (K11 ölçümünün veri kaynağı)
    yanit = istemci.post(
        f"/olaylar/{olay_id}/durum",
        data={"durum": "false_alarm", "not_metni": "gölge yansıması"},
        follow_redirects=False,
    )
    assert yanit.status_code == 303
    detay = istemci.get(f"/olaylar/{olay_id}").text
    assert "Yanlış alarm" in detay
    assert "gölge yansıması" in detay


def test_olay_filtresi(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera_id = _kamera_olustur(baglanti)
        ihlal_yaz(
            baglanti,
            test_ayarlari,
            _ornek_ihlal(kamera_id, 1),
            {"rule_type": "zone_intrusion"},
            None,
        )
        sistem_olayi_yaz(baglanti, "Disk azalıyor")
    finally:
        baglanti.close()

    yalniz_sistem = istemci.get("/olaylar?tip=system").text
    assert "Disk azalıyor" in yalniz_sistem
    assert "Bölge ihlali" not in yalniz_sistem


def test_csv_disa_aktarma(istemci, test_ayarlari):
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        kamera_id = _kamera_olustur(baglanti)
        ihlal_yaz(
            baglanti,
            test_ayarlari,
            _ornek_ihlal(kamera_id, 1),
            {"rule_type": "zone_intrusion"},
            None,
        )
    finally:
        baglanti.close()
    yanit = istemci.get("/olaylar/disa-aktar.csv")
    assert yanit.status_code == 200
    assert "Bölge ihlali" in yanit.text
    assert "Zaman;Tip;Kamera" in yanit.text


def test_goruntu_yolu_disari_cikamaz(istemci):
    # Yol kaçışı (path traversal) — .env veya veritabanı dışarı sızmamalı
    yanit = istemci.get("/goruntuler/../dalsan.db")
    assert yanit.status_code == 404
    yanit = istemci.get("/goruntuler/..%2F..%2F.env")
    assert yanit.status_code == 404


def test_yedekleme(istemci, test_ayarlari):
    yanit = istemci.post("/yedekle", follow_redirects=False)
    assert yanit.status_code == 303
    yedekler = list((test_ayarlari.veri_dizini / "yedekler").glob("dalsan-*.db"))
    assert len(yedekler) == 1
    # Yedek geçerli bir SQLite dosyası mı ve tablolar içinde mi?
    kopya = veritabani.baglanti_ac(yedekler[0])
    try:
        assert "cameras" in veritabani.tablo_adlari(kopya)
    finally:
        kopya.close()
