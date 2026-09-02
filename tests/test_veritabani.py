"""Veritabanı bağlantısı ve şema uygulaması testleri."""

from __future__ import annotations

import sqlite3

import pytest

from app import veritabani, zaman
from app.hatalar import VeritabaniHatasi
from tests.sema_bilgisi import SEMA_BETIK_SAYISI, SON_SEMA_SURUMU

BEKLENEN_TABLOLAR = {
    "cameras",
    "camera_calibrations",
    "zones",
    "rules",
    "events",
    "announcement_messages",
    "ppe_samples",
    # 002 — hoparlör bölgeleri: anonsun hangi adrese gideceği
    "speaker_zones",
}


@pytest.fixture
def baglanti(tmp_path):
    baglanti = veritabani.baglanti_ac(tmp_path / "test.db")
    veritabani.semayi_uygula(baglanti)
    yield baglanti
    baglanti.close()


def test_beklenen_tablolar_ve_surum_tablosu_olusuyor(baglanti):
    tablolar = set(veritabani.tablo_adlari(baglanti))
    assert tablolar == BEKLENEN_TABLOLAR | {"sema_surumu"}
    assert veritabani.mevcut_surum(baglanti) == SON_SEMA_SURUMU


def test_wal_modu_acik(baglanti):
    mod = baglanti.execute("PRAGMA journal_mode").fetchone()[0]
    assert mod == "wal"


def test_sema_iki_kez_uygulanabiliyor(baglanti):
    # İkinci uygulama hata vermemeli, hiçbir şeyi ikilememeli (idempotent).
    veritabani.semayi_uygula(baglanti)
    surumler = baglanti.execute("SELECT COUNT(*) FROM sema_surumu").fetchone()[0]
    assert surumler == SEMA_BETIK_SAYISI
    mesajlar = baglanti.execute("SELECT COUNT(*) FROM announcement_messages").fetchone()[0]
    assert mesajlar == 5


def test_anons_mesajlari_seed_edilmis(baglanti):
    anahtarlar = {
        satir["key"] for satir in baglanti.execute("SELECT key FROM announcement_messages")
    }
    assert anahtarlar == {"safe_distance", "pedestrian_path", "vehicle_position", "helmet", "vest"}


def test_yabanci_anahtar_zorlaniyor(baglanti):
    # Olmayan kameraya bölge eklemek REDDEDİLMELİ. SQLite bunu varsayılan
    # olarak zorlamaz; baglanti_ac() PRAGMA foreign_keys = ON veriyor.
    with pytest.raises(sqlite3.IntegrityError):
        baglanti.execute(
            "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
            "VALUES (999, 'test', 'pedestrian_path', '[[0,0],[1,0],[1,1]]', ?)",
            (zaman.simdi_utc(),),
        )


def test_bozuk_betik_hicbir_sey_birakmaz(tmp_path):
    # Betik ile sürüm kaydı TEK transaction: betik yarıda patlarsa ne tablo
    # kalmalı ne sürüm kaydı — aksi halde sistem bir daha açılamaz.
    sema = tmp_path / "sema"
    sema.mkdir()
    (sema / "001_kotu.sql").write_text(
        "CREATE TABLE deneme (x INTEGER);\nCREATE TABLE deneme (x INTEGER);",  # ikincisi patlar
        encoding="utf-8",
    )
    baglanti = veritabani.baglanti_ac(tmp_path / "t.db")
    try:
        with pytest.raises(VeritabaniHatasi):
            veritabani.semayi_uygula(baglanti, sema)
        assert veritabani.tablo_adlari(baglanti) == ["sema_surumu"]
        kayit = baglanti.execute("SELECT COUNT(*) FROM sema_surumu").fetchone()[0]
        assert kayit == 0
    finally:
        baglanti.close()


def test_bozuk_veritabani_dosyasi_turkce_hata_veriyor(tmp_path):
    bozuk = tmp_path / "bozuk.db"
    bozuk.write_text("bu bir veritabanı değil", encoding="utf-8")
    with pytest.raises(VeritabaniHatasi) as hata:
        veritabani.baglanti_ac(bozuk)
    assert "yedek" in hata.value.kullanici_mesaji  # kullanıcıya çözüm yolu söyleniyor


def test_kamera_silinince_bolge_de_siliniyor(baglanti):
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, source_type, source_url, created_at, updated_at) "
        "VALUES (1, 'test-kamera', 'file', 'video.mp4', ?, ?)",
        (simdi, simdi),
    )
    baglanti.execute(
        "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
        "VALUES (1, 'test', 'ppe_required', '[[0,0],[1,0],[1,1]]', ?)",
        (simdi,),
    )
    baglanti.execute("DELETE FROM cameras WHERE id = 1")
    kalan = baglanti.execute("SELECT COUNT(*) FROM zones").fetchone()[0]
    assert kalan == 0  # ON DELETE CASCADE
