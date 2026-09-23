-- 007_olay_yasam_dongusu.sql  (Faz 2c — docs/17 §8.2)
--
-- İKİ İŞ:
--  1) zones YENİDEN KURULUR: zone_type CHECK (001_ilk.sql) kalkar. Tipin tek
--     doğruluk kaynağı artık saf katmanda app/rules/tipler.py BOLGE_TIPI_KODLARI
--     (web/ortak.py BOLGE_TIPLERI yalnız Türkçe ad eşler); yazım yolu
--     web/kameralar.py:_bolge_tipi_dogrula, yükleme yolu süpervizör.
--     Yeni tipler: crossing (yaya-araç geçidi), ppe_exempt (KKD muaf alan).
--  2) EKLEMELİ: events sütunları (olay kodu, önem, bitiş), anons mesajı damgası +
--     3 yeni anons mesajı, analysis_hours ve ppe_collection_gate tabloları.
--
-- Kalibrasyon kontrol ölçümü sütunları (camera_calibrations.check_*) BU BETİKTE
-- YOK: docs/17 S7 cevaplanmadı ve varsayılanı "kontrol ölçümü koşullu, kodlanmaz".
-- Cevap "evet" olursa ayrı bir göçle eklenir.
--
-- TEHLİKE (005 ile aynı): rules.zone_id → zones ON DELETE CASCADE. Yabancı anahtar
-- AÇIKKEN `DROP TABLE zones` bölgeye bağlı TÜM kuralları siler. İşaret satırı
-- zorunludur: app/veritabani.py bu betiği işlem DIŞINDA foreign_keys=OFF ile
-- çalıştırır, sonra foreign_key_check yapar. Denetim COMMIT'ten SONRA koştuğu
-- için kurulu bir veritabanında bu betikten ÖNCE otomatik yedek alınır
-- (docs/17 §8.4).
--
-- DALSAN-SEMA: YABANCI-ANAHTAR-KAPALI
--
-- Betikler BEGIN/COMMIT İÇERMEZ; sarmalamayı app/veritabani.py yapar. Yeni
-- sütunlara CHECK konmaz (değer listeleri Python'da tek yerde doğrulanır); zaman
-- sütunlarına SQL DEFAULT verilmez (app/zaman.py yazar).

-- ------------------------------------------------------------ 1) zones
CREATE TABLE zones_yeni (
    id         INTEGER PRIMARY KEY,
    camera_id  INTEGER NOT NULL
               REFERENCES cameras (id) ON DELETE CASCADE, -- bölge kamerasız yaşayamaz
    name       TEXT    NOT NULL,
    -- CHECK YOK (bilerek, docs/17 §4.5). Geçerli değerler: pedestrian_path,
    -- loading_area, truck_parking, vehicle_area, ppe_required, restricted,
    -- crossing, ppe_exempt (app/rules/tipler.py BOLGE_TIPI_KODLARI)
    zone_type  TEXT    NOT NULL,
    polygon    TEXT    NOT NULL,   -- JSON: normalize (0-1) [[x,y], ...], en az 3 nokta
    enabled    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT    NOT NULL    -- ISO-8601 UTC
);

-- Sütunlar TEK TEK (005 gerekçesi). id'ler korunur → rules.zone_id geçerli kalır.
INSERT INTO zones_yeni (id, camera_id, name, zone_type, polygon, enabled, updated_at)
SELECT id, camera_id, name, zone_type, polygon, enabled, updated_at FROM zones;

DROP TABLE zones;

ALTER TABLE zones_yeni RENAME TO zones;
-- (001'de zones üzerinde indeks yok; yeniden kurulacak indeks yok.)

-- ------------------------------------------------------------ 2) events
-- PPE_NO_HELMET … CAMERA_DOWN (app/rules/olay_kodu.py). NULL = 007 öncesi olay.
ALTER TABLE events ADD COLUMN event_code  TEXT;
-- critical | high | medium | low | system (Python'da doğrulanır)
ALTER TABLE events ADD COLUMN severity    TEXT;
-- ISO-8601 UTC. NULL = olay SÜRÜYOR. Anlık olaylarda occurred_at ile aynı.
ALTER TABLE events ADD COLUMN resolved_at TEXT;

-- 007 öncesi olayların hepsi anlıktı; "sürüyor" görünmesinler.
UPDATE events SET resolved_at = occurred_at WHERE resolved_at IS NULL;

CREATE INDEX idx_events_code_occurred ON events (event_code, occurred_at);
-- KISMİ DEĞİL: hem açılışta asılı olayları kapatma / "sürüyor" filtresi
-- (resolved_at IS NULL) hem canlı akışın "resolved_at > son bakış" sorgusu aynı
-- indeksi kullanır. Kısmi indeks ikinci sorguya yaramazdı.
CREATE INDEX idx_events_resolved ON events (resolved_at);

-- ------------------------------------------------------------ 3) analysis_hours
-- "Yanlış alarm / saat / kamera" ve çalışma süresi için PAYDA. Süpervizör
-- birkaç dakikada bir upsert eder (INSERT … ON CONFLICT DO UPDATE).
CREATE TABLE analysis_hours (
    camera_id        INTEGER NOT NULL,   -- FK YOK: kamera silinse de ölçüm geçmişi kalır
    hour_utc         TEXT    NOT NULL,   -- 'YYYY-MM-DDTHH'
    -- Tespitçi yüklüyken işlenen ardışık kareler arasındaki süreler toplanır;
    -- kopukluk ve model yokluğu boşlukları SAYILMAZ.
    analyzed_s       REAL    NOT NULL DEFAULT 0,
    frames_processed INTEGER NOT NULL DEFAULT 0,
    frames_failed    INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (camera_id, hour_utc)
);

-- ------------------------------------------------------------ 4) announcement_messages
-- R19: mesaj ya da WAV değişikliği çalışan sisteme insin; süpervizörün
-- yapılandırma damgasına COALESCE(MAX(updated_at), '') olarak girer.
-- Yazan yol: web/anons_web.py (mesaj kaydı).
ALTER TABLE announcement_messages ADD COLUMN updated_at TEXT;
-- Ek hazır kurallar (yaya yolunda araç, araç yolunda yaya) ve yasak alan bunlara
-- bağlanır. Metinler TASLAKTIR (docs/17 S21); Anons sayfasından değiştirilir.
INSERT OR IGNORE INTO announcement_messages (key, text) VALUES
    ('vehicle_on_walkway',     'Dikkat, yaya yolunda araç var.'),
    ('person_in_vehicle_lane', 'Lütfen araç yolundan çıkınız.'),
    ('restricted_entry',       'Bu alana giriş yasaktır.');

-- ------------------------------------------------------------ 5) ppe_collection_gate
-- KKD veri toplama kapısı (docs/17 K17). .env'de DEĞİL: çalışırken açılıp
-- kapanır, Docker'da da yazılabilir. Tek satır (id = 1); örnekleme her
-- örnekten önce okur (Faz 2e).
CREATE TABLE ppe_collection_gate (
    id         INTEGER PRIMARY KEY,   -- her zaman 1
    enabled    INTEGER NOT NULL DEFAULT 0,
    changed_at TEXT,                  -- ISO-8601 UTC; NULL = hiç değiştirilmedi
    note       TEXT                   -- "Rev.02 imzalandı" onay metni
);
-- Başlangıç: KAPALI (docs/17 S10 varsayılanı).
INSERT INTO ppe_collection_gate (id, enabled) VALUES (1, 0);

-- rules: ŞEMA DEĞİŞMEZ. severity DEFAULT 'warning' kalır; kodda "olay kodunun
-- varsayılanı" demektir. Veri güncellenmez.
