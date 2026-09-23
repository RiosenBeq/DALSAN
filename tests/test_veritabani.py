"""Veritabanı bağlantısı ve şema uygulaması testleri."""

from __future__ import annotations

import re
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
    # 002 - hoparlör bölgeleri: anonsun hangi adrese gideceği
    "speaker_zones",
    # 003 - nesne kütüphanesi: kullanıcının fotoğrafla tanıttığı kendi nesneleri
    "library_objects",
    "library_object_photos",
    # 004 - nesne teşhisi: "bu nesne ne kadar tanınabilir" ölçümünün önbelleği
    "library_object_diagnosis",
    # 007 - analiz edilen süre (yanlış alarm / saat paydası) ve KKD toplama kapısı
    "analysis_hours",
    "ppe_collection_gate",
    # 009 - uyarı teslim kaydı (docs/17 §7.3-10)
    "alert_deliveries",
}


def _tohum_mesaj_anahtarlari() -> set[str]:
    """Şema betiklerindeki anons mesajı tohumları (elle sayı yazılmaz, §4.6)."""
    from tests.sema_bilgisi import SEMA_DIZINI

    anahtarlar: set[str] = set()
    for betik in sorted(SEMA_DIZINI.glob("*.sql")):
        metin = betik.read_text(encoding="utf-8")
        for blok in re.findall(
            r"INSERT (?:OR IGNORE )?INTO announcement_messages[^;]*;", metin, re.S
        ):
            anahtarlar |= set(re.findall(r"\(\s*'([a-z_]+)'\s*,", blok))
    return anahtarlar


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
    assert mesajlar == len(_tohum_mesaj_anahtarlari())


def test_anons_mesajlari_seed_edilmis(baglanti):
    anahtarlar = {
        satir["key"] for satir in baglanti.execute("SELECT key FROM announcement_messages")
    }
    assert anahtarlar == {
        "safe_distance",
        "pedestrian_path",
        "vehicle_position",
        "helmet",
        "vest",
        # 007 - ek hazır kuralların ve yasak alanın mesajları (metinler taslak, S21)
        "vehicle_on_walkway",
        "person_in_vehicle_lane",
        "restricted_entry",
    }
    assert anahtarlar == _tohum_mesaj_anahtarlari()


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
    # kalmalı ne sürüm kaydı - aksi halde sistem bir daha açılamaz.
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
    """Verilen betikten ÖNCEKİ hâliyle kurulmuş bir veritabanı üretir.

    Yalnız sıralı listede verilen betikten ÖNCE gelenler kopyalanır (docs/17
    §8.4). Eskiden yalnız o betik atlanıyordu: "005 öncesi" veritabanı 006 ve
    007 ile kuruluyor, 005 en son uygulanıyordu - gerçek bir güncellemenin
    sırası değil.
    """
    eski_sema = tmp_path / "sema_eski"
    eski_sema.mkdir()
    for yol in sorted(veritabani.SEMA_DIZINI.glob("*.sql")):
        if yol.name >= betik_adi_baslangici:
            break
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


# ------------------------------------------------- 007: olay yaşam döngüsü göçü


def _006_verisi_ekle(yol) -> None:
    """006 hâlindeki veritabanına docs/17 §8.2'deki denemenin verisini ekler."""
    baglanti = veritabani.baglanti_ac(yol)
    simdi = zaman.simdi_utc()
    try:
        for bolge_id, tip in ((2, "pedestrian_path"), (3, "restricted")):
            baglanti.execute(
                "INSERT INTO zones (id, camera_id, name, zone_type, polygon, updated_at) "
                "VALUES (?, 1, ?, ?, '[[0,0],[1,0],[1,1]]', ?)",
                (bolge_id, f"B{bolge_id}", tip, simdi),
            )
        for kural_id, bolge_id in ((2, 2), (3, 3), (4, None)):
            baglanti.execute(
                "INSERT INTO rules (id, camera_id, rule_type, zone_id, target_classes, "
                "params, updated_at) VALUES (?, 1, ?, ?, '[\"person\"]', '{}', ?)",
                (kural_id, "zone_intrusion" if bolge_id else "safe_distance", bolge_id, simdi),
            )
        for olay_id in range(2, 11):
            baglanti.execute(
                "INSERT INTO events (id, occurred_at, event_type, camera_id, rule_id, "
                "rule_snapshot, details) VALUES (?, ?, 'violation', 1, ?, '{}', '{}')",
                (olay_id, simdi, 1 + olay_id % 4),
            )
        baglanti.commit()
    finally:
        baglanti.close()


def _bag_fotografi(baglanti) -> dict[str, list[tuple]]:
    sorgular = {
        "bolgeler": "SELECT id, zone_type FROM zones ORDER BY id",
        "kurallar": "SELECT id, zone_id FROM rules ORDER BY id",
        "olaylar": "SELECT id, rule_id FROM events ORDER BY id",
    }
    return {ad: [tuple(s) for s in baglanti.execute(sql)] for ad, sql in sorgular.items()}


def test_007_goc_bolge_kural_ve_olay_baglarini_korur(tmp_path):
    """zones yeniden kurulurken `rules.zone_id … ON DELETE CASCADE` tuzağı
    açıktır: yabancı anahtar açık kalsaydı bütün bölge kuralları silinirdi."""
    yol = _eski_kurulum(tmp_path, "007")
    _006_verisi_ekle(yol)
    baglanti = veritabani.baglanti_ac(yol)
    try:
        once = {
            ad: [tuple(s) for s in satirlar] for ad, satirlar in _bag_fotografi(baglanti).items()
        }
        veritabani.semayi_uygula(baglanti)
        sonra = {
            ad: [tuple(s) for s in satirlar] for ad, satirlar in _bag_fotografi(baglanti).items()
        }
        assert sonra == once
        assert len(once["bolgeler"]) == 3 and len(once["kurallar"]) == 4
        assert baglanti.execute("PRAGMA foreign_key_check").fetchall() == []
        # 007 öncesi olayların hepsi anlıktı: "sürüyor" görünmezler
        acik_ya_da_farkli = baglanti.execute(
            "SELECT COUNT(*) FROM events WHERE resolved_at IS NULL OR resolved_at != occurred_at"
        ).fetchone()[0]
        assert acik_ya_da_farkli == 0
        # CHECK kalktı: yeni tipler yazılabilir (süzgeç artık kodda)
        baglanti.execute(
            "INSERT INTO zones (camera_id, name, zone_type, polygon, updated_at) "
            "VALUES (1, 'Geçit', 'crossing', '[[0,0],[1,0],[1,1]]', ?)",
            (zaman.simdi_utc(),),
        )
        # KKD toplama kapısı kapalı doğar (docs/17 S10)
        kapi = [tuple(s) for s in baglanti.execute("SELECT id, enabled FROM ppe_collection_gate")]
        assert kapi == [(1, 0)]
        # CASCADE yerinde: bölge silinince ona bağlı kural da gider
        baglanti.execute("DELETE FROM zones WHERE id = 2")
        assert baglanti.execute("SELECT COUNT(*) FROM rules WHERE id = 2").fetchone()[0] == 0
    finally:
        baglanti.close()


def test_008_goc_kkd_orneklerini_ve_kurallari_korur(tmp_path):
    """008 yalnız sütun ekler (docs/17 §8.3): eski örnek ve kural aynen kalır,
    yeni sütunlar boş doğar; tablo yeniden kurulmadığı için göç yedeği alınmaz."""
    yol = _eski_kurulum(tmp_path, "008")
    baglanti = veritabani.baglanti_ac(yol)
    try:
        baglanti.execute(
            "INSERT INTO ppe_samples (id, camera_id, captured_at, crop_path, helmet_label, "
            "vest_label, source, labeled_at) VALUES (7, 1, '2026-09-01T09:00:00+00:00', "
            "'kkd-ornekler/a.jpg', 'yes', 'no', 'auto', '2026-09-01T10:00:00+00:00')"
        )
        baglanti.commit()
        once = [tuple(s) for s in baglanti.execute("SELECT * FROM ppe_samples")]
        kural_once = [tuple(s) for s in baglanti.execute("SELECT * FROM rules")]
        veritabani.semayi_uygula(baglanti)
        ornek = dict(baglanti.execute("SELECT * FROM ppe_samples WHERE id = 7").fetchone())
        assert tuple(ornek[k] for k in list(ornek)[: len(once[0])]) == once[0]
        assert ornek["person_height_px"] is None and ornek["sharpness"] is None
        assert ornek["hard_case"] is None
        kural = dict(baglanti.execute("SELECT * FROM rules WHERE id = 1").fetchone())
        assert tuple(kural[k] for k in list(kural)[: len(kural_once[0])]) == kural_once[0]
        assert kural["approved_model_version"] is None
        assert baglanti.execute("PRAGMA foreign_key_check").fetchall() == []
    finally:
        baglanti.close()
    assert not list(tmp_path.glob("yedekler/goc-oncesi-008*"))


def test_009_goc_hoparlor_satirlarini_http_kanali_yapar(tmp_path):
    """009 yalnız sütun ekler: eski hoparlör bölgeleri (002, hepsi HTTP) aynen
    kalır ve `http` kanalı olarak sınıflanır; sağlık henüz yoklanmadı (NULL)."""
    yol = _eski_kurulum(tmp_path, "009")
    baglanti = veritabani.baglanti_ac(yol)
    try:
        simdi = zaman.simdi_utc()
        baglanti.execute(
            "INSERT INTO speaker_zones (id, name, area, address, enabled, created_at, "
            "updated_at) VALUES (3, 'Sevkiyat', 'Sevkiyat', 'http://10.0.0.9/anons', 1, ?, ?)",
            (simdi, simdi),
        )
        baglanti.commit()
        once = tuple(baglanti.execute("SELECT * FROM speaker_zones WHERE id = 3").fetchone())
        veritabani.semayi_uygula(baglanti)
        satir = dict(baglanti.execute("SELECT * FROM speaker_zones WHERE id = 3").fetchone())
        assert tuple(satir[k] for k in list(satir)[: len(once)]) == once
        assert (satir["kind"], satir["device"], satir["health"]) == ("http", "", None)
        assert baglanti.execute("SELECT COUNT(*) FROM alert_deliveries").fetchone()[0] == 0
    finally:
        baglanti.close()
    assert not list(tmp_path.glob("yedekler/goc-oncesi-009*"))


def test_bos_veritabaninda_goc_yedegi_olusmaz(tmp_path):
    """Yeni kurulumda (ve testlerde) her çağrı boş bir yedek bırakırdı."""
    baglanti = veritabani.baglanti_ac(tmp_path / "yeni.db")
    try:
        veritabani.semayi_uygula(baglanti)
    finally:
        baglanti.close()
    assert not (tmp_path / "yedekler").exists()


def test_kurulu_veritabaninda_isaretli_betikten_once_yedek_alinir(tmp_path):
    """Bütünlük denetimi COMMIT'ten sonra koşar: bozukluk bulunursa tek
    kurtarma yolu göçten ÖNCEKİ kopyadır."""
    yol = _eski_kurulum(tmp_path, "007")
    baglanti = veritabani.baglanti_ac(yol)
    try:
        veritabani.semayi_uygula(baglanti)
    finally:
        baglanti.close()
    yedekler = sorted((tmp_path / "yedekler").glob("goc-oncesi-007_*.db"))
    assert len(yedekler) == 1
    kopya = sqlite3.connect(yedekler[0])
    try:
        surumler = {satir[0] for satir in kopya.execute("SELECT surum FROM sema_surumu")}
        assert kopya.execute("SELECT COUNT(*) FROM rules").fetchone()[0] == 1
    finally:
        kopya.close()
    assert "006_video_tek_gecis.sql" in surumler
    assert "007_olay_yasam_dongusu.sql" not in surumler


def test_yedek_alinamazsa_goc_yapilmaz(tmp_path):
    yol = _eski_kurulum(tmp_path, "007")
    (tmp_path / "yedekler").write_text("klasör değil, dosya", encoding="utf-8")
    baglanti = veritabani.baglanti_ac(yol)
    try:
        with pytest.raises(VeritabaniHatasi) as hata:
            veritabani.semayi_uygula(baglanti)
        assert "güncelleme YAPILMADI" in hata.value.kullanici_mesaji
        surumler = {s["surum"] for s in baglanti.execute("SELECT surum FROM sema_surumu")}
        assert "007_olay_yasam_dongusu.sql" not in surumler
    finally:
        baglanti.close()
