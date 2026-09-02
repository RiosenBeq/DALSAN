-- 002_hoparlor_bolgeleri_ve_golge_mod.sql
--
-- İKİ EKLEME. Bu betikte YALNIZCA "CREATE TABLE" ve "ALTER TABLE ... ADD COLUMN"
-- vardır; hiçbir mevcut tablo yeniden kurulmaz, düşürülmez, CHECK kısıtı
-- değiştirilmez.
--
-- NEDEN BU KADAR KATI: app/veritabani.py her bağlantıda "PRAGMA foreign_keys = ON"
-- verir, ama şema betiklerini BEGIN/COMMIT içinde çalıştırır ve SQLite'ta bu
-- PRAGMA bir işlemin İÇİNDE etkisizdir. `zones` ya da `rules` tablosunu
-- "yeniden kur + kopyala" yöntemiyle değiştiren bir betik, kullanıcının
-- kameralarına bağlı TÜM bölge ve kurallarını sessizce silerdi.
-- 001_ilk.sql'e de asla dokunulmaz: kurulu sistemlerde çoktan uygulanmıştır.
--
-- Betikler BEGIN/COMMIT İÇERMEZ; sarmalamayı app/veritabani.py yapar.

-- --------------------------------------------------------- hoparlör bölgeleri
--
-- Bugüne kadar tek bir anons adresi vardı (.env → ANONS_HTTP_ADRESI) ve ihlal
-- hangi bölümde olursa olsun aynı hoparlörden duyuruluyordu. Bu tablo, anonsun
-- YALNIZCA ihlalin olduğu bölümde çalmasını sağlar: fabrikanın öbür ucundaki
-- çalışan, kendisiyle ilgisi olmayan bir uyarıyı duymaz.
--
-- `area` fabrika bölümüdür ve cameras.area ile AYNI düz metindir (ADR-007).
-- Ayrı bir "bölümler" tablosu kurulmadı: bugün alanlar zaten düz metin ve
-- kullanıcıya öğrenmesi gereken ikinci bir kavram çıkarmak istemiyoruz.
-- Boş `area` = "tüm fabrika": eşleşen bölüm bulunamazsa bu bölge kullanılır.
--
-- `address` arayüzde MASKELİ gösterilir (kullanıcı adı/şifre içeren adres
-- ekrana ham basılmaz) — kamera RTSP adresiyle aynı desen.
CREATE TABLE speaker_zones (
    id                INTEGER PRIMARY KEY,
    name              TEXT    NOT NULL,
    area              TEXT    NOT NULL DEFAULT '',  -- cameras.area ile eşleşir; '' = tüm fabrika
    address           TEXT    NOT NULL,             -- http(s) adresi; ekranda MASKELİ
    description       TEXT    NOT NULL DEFAULT '',
    enabled           INTEGER NOT NULL DEFAULT 1,
    last_announced_at TEXT,                         -- ISO-8601 UTC; son BAŞARILI anons
    created_at        TEXT    NOT NULL,             -- ISO-8601 UTC
    updated_at        TEXT    NOT NULL              -- ISO-8601 UTC
);

-- Anons gönderilirken "bu bölümün hoparlörü hangisi" sorgusu her ihlalde çalışır.
CREATE INDEX idx_speaker_zones_area ON speaker_zones (area);

-- --------------------------------------------------------------- gölge mod
--
-- Gölge mod = kural ÇALIŞIR ve olay YAZAR, ama hoparlörden anons çalmaz ve
-- ekranda uyarı bandı çıkmaz. Yeni kurulan bir kuralın güvenli deneme yoludur:
-- docs/04 §8.2 KKD'nin devreye alınmasını bu adımla tarif eder ("3 gün aktif
-- ama anonssuz çalışır"), docs/07 §3.5 de her yeni bölüm için aynı döngüyü
-- şart koşar. İlk günden anonsla başlamak, sistem henüz ayarlanmamışken
-- çalışanı yanlış uyarır ve bir daha düzelmeyen bir güven kaybı yaratır.
--
-- Varsayılan 0: bugüne kadar kurulmuş kuralların davranışı DEĞİŞMEZ.
ALTER TABLE rules ADD COLUMN shadow_mode INTEGER NOT NULL DEFAULT 0;
