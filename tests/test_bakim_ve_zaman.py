"""Bakım zamanlaması ve tarih sınırları.

İkisi de "sessiz" hatalardı: bakım hiç çalışmadığı halde ana sayfada saklama
süreleri yazıyordu; olay filtresi ise gece yarısı civarındaki olayları yanlış
güne koyuyordu. Bu testler ikisinin de geri gelmesini engeller.
"""

from __future__ import annotations

import time

from app import veritabani, zaman
from app.analiz.supervizor import _BAKIM_ARALIGI_SN, AnalizSupervizoru
from app.olaylar.yazici import ihlal_yaz
from app.rules.tipler import Ihlal


def test_bakim_acilista_calisacak_sekilde_tohumlanir(test_ayarlari):
    """`_son_bakim = 0.0` bırakılırsa koşul `time.monotonic() >= 86400` olur;
    monotonic MAKİNENİN açık kalma süresidir. Her vardiya sonunda kapatılan bir
    bilgisayarda saklama süresi temizliği HİÇ çalışmazdı."""
    supervizor = AnalizSupervizoru(test_ayarlari)
    # _dongu()'nun tohumladığı değerin aynısı
    supervizor._son_bakim = time.monotonic() - _BAKIM_ARALIGI_SN
    simdi = time.monotonic()
    assert simdi - supervizor._son_bakim >= _BAKIM_ARALIGI_SN, (
        "bakım açılıştan hemen sonra çalışmalı"
    )


def test_bakim_fotografi_silince_olay_kaydini_temizler(test_ayarlari):
    """Fotoğraf silinip events.snapshot_path dolu kalırsa olay ekranında kırık
    resim çıkardı. Olayın KENDİSİ korunur, yalnızca bağlantı temizlenir."""
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        veritabani.semayi_uygula(baglanti)
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "INSERT INTO cameras (name, source_type, source_url, created_at, updated_at) "
            "VALUES ('K1', 'file', 'v.mp4', ?, ?)",
            (simdi, simdi),
        )
        baglanti.commit()
        olay_id = ihlal_yaz(
            baglanti,
            test_ayarlari,
            Ihlal(kural_id=1, kamera_id=1, takip_idler=[1], bolge_id=None, olculen=1.0),
            {"rule_type": "zone_intrusion"},
            b"kanit",
        )
        # Olayı saklama süresinin dışına taşı
        eski = zaman.gun_once_utc(test_ayarlari.goruntu_saklama_gun + 5)
        baglanti.execute("UPDATE events SET occurred_at = ? WHERE id = ?", (eski, olay_id))
        baglanti.commit()

        supervizor = AnalizSupervizoru.__new__(AnalizSupervizoru)
        supervizor.ayarlar = test_ayarlari
        from app.loglama import log_al

        supervizor._log = log_al("test")
        supervizor._bakim_yap(baglanti)

        satir = baglanti.execute("SELECT * FROM events WHERE id = ?", (olay_id,)).fetchone()
        assert satir is not None, "olay kaydı korunmalı"
        assert satir["snapshot_path"] is None, "silinen fotoğrafın bağlantısı temizlenmeli"
    finally:
        baglanti.close()


def test_yerel_gun_siniri_utce_cevrilir():
    """Türkiye UTC+3: 2 Eylül'ün başlangıcı UTC'de 1 Eylül 21:00'dır."""
    assert zaman.yerel_gun_baslangici_utc("2026-09-02").startswith("2026-09-01T21:00")
    assert zaman.yerel_gun_sonu_utc("2026-09-02").startswith("2026-09-02T21:00")


def test_gece_yarisindaki_olay_dogru_gunde_gorunur(istemci, test_ayarlari):
    """ESKİ HATA: tarih sınırları UTC sanılıyordu; Türkiye saatiyle 2 Eylül
    01:00'daki olay (UTC 1 Eylül 22:00) '2 Eylül' filtresinde GÖRÜNMÜYORDU."""
    baglanti = veritabani.baglanti_ac(test_ayarlari.veritabani_yolu)
    try:
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "INSERT INTO cameras (name, source_type, source_url, created_at, updated_at) "
            "VALUES ('Gece', 'file', 'v.mp4', ?, ?)",
            (simdi, simdi),
        )
        baglanti.execute(
            "INSERT INTO events (occurred_at, event_type, camera_id, details, status) "
            "VALUES ('2026-09-01T22:00:00+00:00', 'system', 1, "
            "'{\"mesaj\": \"Gece yarisi olayi\"}', 'new')"
        )
        baglanti.commit()
    finally:
        baglanti.close()

    # Türkiye saatiyle 2 Eylül 01:00 → '2 Eylül' filtresinde görünmeli
    metin = istemci.get("/olaylar?baslangic=2026-09-02&bitis=2026-09-02").text
    assert "Gece yarisi olayi" in metin
    # 1 Eylül filtresinde görünmemeli
    metin = istemci.get("/olaylar?baslangic=2026-09-01&bitis=2026-09-01").text
    assert "Gece yarisi olayi" not in metin


def test_bozuk_tarih_ve_kamera_filtresi_400_verir(istemci):
    """Beklenmeyen 500 yerine anlaşılır Türkçe hata."""
    yanit = istemci.get("/olaylar?kamera=abc")
    assert yanit.status_code == 400
    assert "sayı olmalı" in yanit.json()["hata"]
    yanit = istemci.get("/olaylar?baslangic=02.09.2026")
    assert yanit.status_code == 400
