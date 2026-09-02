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


def test_ayni_saniyede_iki_ihlal_ayri_fotograf(test_ayarlari):
    # Kanıt fotoğrafları birbirini EZMEMELİ (dosya adı saniye çözünürlüklü)
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        kamera_id = _kamera_olustur(baglanti)
        id1 = ihlal_yaz(baglanti, test_ayarlari, _ornek_ihlal(kamera_id, 1), {}, b"kanit-1")
        id2 = ihlal_yaz(baglanti, test_ayarlari, _ornek_ihlal(kamera_id, 1), {}, b"kanit-2")
        yol1 = baglanti.execute("SELECT snapshot_path FROM events WHERE id = ?", (id1,)).fetchone()[
            0
        ]
        yol2 = baglanti.execute("SELECT snapshot_path FROM events WHERE id = ?", (id2,)).fetchone()[
            0
        ]
        assert yol1 != yol2
        assert (test_ayarlari.goruntu_klasoru / yol1).read_bytes() == b"kanit-1"
        assert (test_ayarlari.goruntu_klasoru / yol2).read_bytes() == b"kanit-2"
    finally:
        baglanti.close()


def test_silinmis_kamera_olayi_dusurmez(test_ayarlari):
    # Kamera, değerlendirme ile kayıt arasında silinirse olay FK hatasıyla
    # KAYBOLMAMALI — kamerasız kaydedilmeli
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        olay_id = ihlal_yaz(
            baglanti, test_ayarlari, _ornek_ihlal(kamera_id=999, kural_id=999), {}, None
        )
        satir = baglanti.execute("SELECT * FROM events WHERE id = ?", (olay_id,)).fetchone()
        assert satir["camera_id"] is None
        assert satir["rule_id"] is None
        sistem_olayi_yaz(baglanti, "Kamera çevrimdışı", kamera_id=999)
    finally:
        baglanti.close()


def test_retention_etiketli_kkd_ornegine_dokunmaz(test_ayarlari):
    """Eğitim veri seti retention'a kurban gitmemeli (docs/06 §5)."""
    import os
    import time as time_mod

    from app.analiz.supervizor import AnalizSupervizoru

    supervizor = AnalizSupervizoru.__new__(AnalizSupervizoru)  # thread başlatmadan
    eski_mtime = time_mod.time() - 200 * 86400  # 200 gün önce

    olay_foto = test_ayarlari.goruntu_klasoru / "2026-01" / "olay.jpg"
    kkd_foto = test_ayarlari.goruntu_klasoru / "kkd-ornekler" / "2026-01" / "ornek.jpg"
    for dosya in (olay_foto, kkd_foto):
        dosya.parent.mkdir(parents=True, exist_ok=True)
        dosya.write_bytes(b"jpeg")
        os.utime(dosya, (eski_mtime, eski_mtime))

    silinen = supervizor._eski_dosyalari_sil(
        test_ayarlari.goruntu_klasoru, 90, test_ayarlari.nesne_klasoru
    )
    assert silinen == 1
    assert not olay_foto.exists()  # eski olay fotoğrafı silindi
    assert kkd_foto.exists()  # KKD örneği (etiketli olabilir) KORUNDU


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


def test_not_eklemek_inceleme_damgasini_kaydirmaz(istemci, test_ayarlari):
    """Sadece not yazmak reviewed_at'i BUGÜNE çekmemeli.

    Neden önemli: reviewed_at, K11 isabet ölçümünün ve "ihlal ne kadar sürede
    incelendi" sorusunun veri kaynağıdır. Kullanıcı günler sonra bir olaya not
    eklediğinde damga o güne kayarsa, olay o gün incelenmiş gibi görünür ve
    ölçüm sessizce bozulur. Gerçek bir inceleme KARARI (durum değişikliği) ise
    damgayı yenilemelidir — iki davranış da burada çivileniyor.
    """
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
    finally:
        baglanti.close()

    def damga_ve_durum() -> tuple[str | None, str]:
        baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
        try:
            satir = baglanti.execute(
                "SELECT reviewed_at, status FROM events WHERE id = ?", (olay_id,)
            ).fetchone()
            return satir["reviewed_at"], satir["status"]
        finally:
            baglanti.close()

    # 1) İlk inceleme kararı: damga BASILIR.
    istemci.post(
        f"/olaylar/{olay_id}/durum",
        data={"durum": "reviewed", "not_metni": ""},
        follow_redirects=False,
    )
    ilk_damga, durum = damga_ve_durum()
    assert durum == "reviewed"
    assert ilk_damga is not None, "İlk inceleme kararı reviewed_at damgalamalı"

    # Damgayı BİLEREK geçmişe çekiyoruz. Zorunlu: zaman.simdi_utc() saniye
    # çözünürlüğünde olduğu için arka arkaya iki istek AYNI damgayı üretir ve
    # "damga kaymadı" kontrolü hatalı kodda da geçerdi (denendi: geçti).
    # Geçmiş bir değerle kontrol, saate hiç bağlı olmadan kesin sonuç verir.
    GECMIS_DAMGA = "2026-08-30T09:15:00+00:00"
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        baglanti.execute("UPDATE events SET reviewed_at = ? WHERE id = ?", (GECMIS_DAMGA, olay_id))
        baglanti.commit()
    finally:
        baglanti.close()

    # 2) Aynı durumda SADECE not eklendi: damga AYNEN kalmalı.
    istemci.post(
        f"/olaylar/{olay_id}/durum",
        data={"durum": "reviewed", "not_metni": "vinç operatörüyle konuşuldu"},
        follow_redirects=False,
    )
    not_sonrasi, durum = damga_ve_durum()
    assert durum == "reviewed"
    assert not_sonrasi == GECMIS_DAMGA, (
        "Sadece not eklemek inceleme damgasını bugüne kaydırdı — K11 ölçümü bozulur"
    )
    assert "vinç operatörüyle konuşuldu" in istemci.get(f"/olaylar/{olay_id}").text

    # 3) Gerçek karar değişikliği: damga YENİLENİR (geçmişte kalmamalı).
    istemci.post(
        f"/olaylar/{olay_id}/durum",
        data={"durum": "false_alarm", "not_metni": "gölge yansıması"},
        follow_redirects=False,
    )
    karar_sonrasi, durum = damga_ve_durum()
    assert durum == "false_alarm"
    assert karar_sonrasi is not None and karar_sonrasi > GECMIS_DAMGA, (
        "Durum gerçekten değiştiğinde damga yenilenmeli"
    )

    # 4) "Yeni"ye geri alındığında damga TEMİZLENİR (olay incelenmemiş sayılır).
    istemci.post(
        f"/olaylar/{olay_id}/durum",
        data={"durum": "new", "not_metni": ""},
        follow_redirects=False,
    )
    geri_alindi, durum = damga_ve_durum()
    assert durum == "new"
    assert geri_alindi is None, "'Yeni'ye dönen olayda inceleme damgası kalmamalı"
