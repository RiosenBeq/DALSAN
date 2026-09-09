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
    # 003 — nesne kütüphanesi: kullanıcının fotoğrafla tanıttığı kendi nesneleri
    "library_objects",
    "library_object_photos",
    # 004 — nesne teşhisi: "bu nesne ne kadar tanınabilir" ölçümünün önbelleği
    "library_object_diagnosis",
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


# ------------------------------------------------- şema göçünün güvenliği
#
# 005_arac_hizi_kurali.sql, depodaki TEK "tabloyu yeniden kur" betiğidir:
# `rules.rule_type` CHECK kısıtına dördüncü tip eklenebilmesi için tablo
# yeniden kurulur. Yabancı anahtar zorlaması AÇIKKEN `DROP TABLE rules`,
# `events.rule_id ... ON DELETE SET NULL` eylemini tetikler ve TÜM olay
# geçmişinin kural bağlantısı sessizce silinir. Bu testler o sessiz veri
# kaybının geri gelmesini engeller.


def _eski_kurulum(tmp_path, betik_adi_baslangici: str = "005"):
    """Verilen betikten ÖNCEKİ hâliyle kurulmuş bir veritabanı üretir."""
    eski_sema = tmp_path / "sema_eski"
    eski_sema.mkdir()
    for yol in sorted(veritabani.SEMA_DIZINI.glob("*.sql")):
        if yol.name.startswith(betik_adi_baslangici):
            continue
        (eski_sema / yol.name).write_text(yol.read_text(encoding="utf-8"), encoding="utf-8")

    yol = tmp_path / "eski.db"
    baglanti = veritabani.baglanti_ac(yol)
    veritabani.semayi_uygula(baglanti, eski_sema)
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, source_type, source_url, created_at, updated_at) "
        "VALUES (1, 'K1', 'file', 'video.mp4', ?, ?)",
        (simdi, simdi),
    )
    baglanti.execute(
        "INSERT INTO zones (id, camera_id, name, zone_type, polygon, updated_at) "
        "VALUES (1, 1, 'Rampa', 'loading_area', '[[0,0],[1,0],[1,1]]', ?)",
        (simdi,),
    )
    baglanti.execute(
        "INSERT INTO rules (id, camera_id, rule_type, zone_id, target_classes, params, "
        "severity, cooldown_s, enabled, shadow_mode, updated_at) "
        "VALUES (1, 1, 'zone_intrusion', 1, '[\"person\"]', '{\"mode\": \"inside\"}', "
        "'critical', 240, 0, 1, ?)",
        (simdi,),
    )
    baglanti.execute(
        "INSERT INTO events (id, occurred_at, event_type, camera_id, rule_id, "
        "rule_snapshot, details, status) "
        "VALUES (1, ?, 'violation', 1, 1, '{}', '{}', 'reviewed')",
        (simdi,),
    )
    baglanti.commit()
    baglanti.close()
    return yol


def test_kural_tablosu_yeniden_kurulunca_olay_gecmisi_KORUNUR(tmp_path):
    """Göçün TEK önemli sözü: kanıt niteliğindeki olay kaydı kuralıyla
    bağlı kalmalı. Bozulursa geçmiş olayların hangi kuraldan geldiği
    kaybolur ve geri getirilemez."""
    yol = _eski_kurulum(tmp_path)
    baglanti = veritabani.baglanti_ac(yol)
    try:
        veritabani.semayi_uygula(baglanti)  # 005 burada uygulanır
        olay = baglanti.execute("SELECT rule_id FROM events WHERE id = 1").fetchone()
        assert olay["rule_id"] == 1
    finally:
        baglanti.close()


def test_yeniden_kurulan_tabloda_hicbir_alan_kaybolmaz(tmp_path):
    """Sütunlar tek tek kopyalanır; sıra kayması sessizce yanlış veri yazardı."""
    yol = _eski_kurulum(tmp_path)
    baglanti = veritabani.baglanti_ac(yol)
    try:
        veritabani.semayi_uygula(baglanti)
        kural = dict(baglanti.execute("SELECT * FROM rules WHERE id = 1").fetchone())
    finally:
        baglanti.close()
    assert kural["camera_id"] == 1
    assert kural["rule_type"] == "zone_intrusion"
    assert kural["zone_id"] == 1
    assert kural["severity"] == "critical"
    assert kural["cooldown_s"] == 240
    assert kural["enabled"] == 0
    assert kural["shadow_mode"] == 1
    assert kural["params"] == '{"mode": "inside"}'


def test_goc_sonrasi_yabanci_anahtar_yeniden_aciliyor(tmp_path):
    """PRAGMA kapalı KALIRSA veri bütünlüğü sessizce korunmaz olurdu."""
    yol = _eski_kurulum(tmp_path)
    baglanti = veritabani.baglanti_ac(yol)
    try:
        veritabani.semayi_uygula(baglanti)
        assert baglanti.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert baglanti.execute("PRAGMA foreign_key_check").fetchall() == []
        # Yeniden kurulan tablonun yabancı anahtarları da çalışmaya devam etmeli
        baglanti.execute("DELETE FROM cameras WHERE id = 1")
        assert baglanti.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 0
    finally:
        baglanti.close()


def test_yeni_kural_tipi_kabul_ediliyor_uydurma_tip_reddediliyor(baglanti):
    simdi = zaman.simdi_utc()
    baglanti.execute(
        "INSERT INTO cameras (id, name, source_type, source_url, created_at, updated_at) "
        "VALUES (1, 'K1', 'file', 'v.mp4', ?, ?)",
        (simdi, simdi),
    )
    baglanti.execute(
        "INSERT INTO rules (camera_id, rule_type, target_classes, params, updated_at) "
        "VALUES (1, 'vehicle_speed', '[\"forklift\"]', '{}', ?)",
        (simdi,),
    )
    assert baglanti.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 1
    # CHECK kısıtı hâlâ koruyor: yeniden kurulan tablo kısıtı kaybetmemeli
    with pytest.raises(sqlite3.IntegrityError):
        baglanti.execute(
            "INSERT INTO rules (camera_id, rule_type, target_classes, params, updated_at) "
            "VALUES (1, 'uydurma_tip', '[]', '{}', ?)",
            (simdi,),
        )
