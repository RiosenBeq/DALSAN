-- 001_ilk.sql — İlk şema: docs/02-MIMARI.md §3'teki 7 tablo, SQLite'a uyarlanmış.
--
-- PostgreSQL → SQLite uyarlamaları (docs/09 karar #2 ve #6 gereği):
--   * JSONB yerine TEXT (JSON metni; yazılmadan önce Pydantic ile doğrulanır)
--   * timestamptz yerine ISO-8601 UTC metni (üretimi: app/zaman.py — tek kaynak)
--   * boolean yerine INTEGER (0 = hayır, 1 = evet)
--
-- Zaman kolonlarına SQL tarafında DEFAULT verilmez: tüm zaman damgaları
-- app/zaman.py'den gelir; iki ayrı saat kaynağı olmasın (docs/08 R7).
--
-- ÖNEMLİ: Betiklere BEGIN/COMMIT YAZMA. app/veritabani.py, betiği ve
-- sema_surumu kaydını TEK transaction içinde sarmalar — böylece elektrik
-- kesintisinde ya ikisi de uygulanır ya hiçbiri.

-- ---------------------------------------------------------------- kameralar
CREATE TABLE cameras (
    id            INTEGER PRIMARY KEY,
    name          TEXT    NOT NULL,
    area          TEXT    NOT NULL DEFAULT '',   -- bölüm adı, düz metin (ADR-007)
    source_type   TEXT    NOT NULL CHECK (source_type IN ('rtsp', 'file')),
    source_url    TEXT    NOT NULL,              -- arayüzde ve API yanıtlarında MASKELİ gösterilir
    enabled       INTEGER NOT NULL DEFAULT 1,
    sample_fps    REAL    NOT NULL DEFAULT 6,
    status        TEXT    NOT NULL DEFAULT 'offline',
    last_frame_at TEXT,                          -- ISO-8601 UTC
    measured_fps  REAL,
    created_at    TEXT    NOT NULL,              -- ISO-8601 UTC
    updated_at    TEXT    NOT NULL               -- ISO-8601 UTC
);

-- Olay filtrelemede ve fabrika geneli yayılımda kullanılır (ADR-007: alan indeksli).
CREATE INDEX idx_cameras_area ON cameras (area);

-- ------------------------------------------------- kamera kalibrasyonları (1:1)
CREATE TABLE camera_calibrations (
    camera_id     INTEGER PRIMARY KEY
                  REFERENCES cameras (id) ON DELETE CASCADE, -- kamera silinince kalibrasyonu da gider
    image_points  TEXT NOT NULL,   -- JSON: görüntüdeki 4 nokta [[x,y], ...]
    world_points  TEXT NOT NULL,   -- JSON: zemindeki karşılıkları, metre cinsinden
    homography    TEXT NOT NULL,   -- JSON: 3x3 matris
    calibrated_at TEXT NOT NULL    -- ISO-8601 UTC
);

-- ------------------------------------------------------------------ bölgeler
CREATE TABLE zones (
    id         INTEGER PRIMARY KEY,
    camera_id  INTEGER NOT NULL
               REFERENCES cameras (id) ON DELETE CASCADE, -- bölge kamerasız yaşayamaz
    name       TEXT    NOT NULL,
    zone_type  TEXT    NOT NULL CHECK (zone_type IN
                 ('pedestrian_path', 'loading_area', 'truck_parking',
                  'vehicle_area', 'ppe_required', 'restricted')),
    polygon    TEXT    NOT NULL,   -- JSON: normalize (0-1) [[x,y], ...], en az 3 nokta
    enabled    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT    NOT NULL    -- ISO-8601 UTC
);

-- ------------------------------------------------------------ anons mesajları
CREATE TABLE announcement_messages (
    id         INTEGER PRIMARY KEY,
    key        TEXT    NOT NULL UNIQUE,
    text       TEXT    NOT NULL,
    audio_file TEXT,               -- kayıtlı WAV dosyası; boşsa yalnız ekran uyarısı
    enabled    INTEGER NOT NULL DEFAULT 1
);

-- 5 temel mesaj (docs/02-MIMARI.md §3: mesafe, yaya yolu, araç konumu, baret, yelek)
INSERT INTO announcement_messages (key, text) VALUES
    ('safe_distance',    'Lütfen iş makinelerinden güvenli mesafede durunuz.'),
    ('pedestrian_path',  'Lütfen yaya yolunu kullanınız.'),
    ('vehicle_position', 'Lütfen aracınızı belirlenen alana konumlandırınız.'),
    ('helmet',           'Lütfen baretinizi takınız.'),
    ('vest',             'Lütfen reflektörlü yeleğinizi giyiniz.');

-- ------------------------------------------------------------------- kurallar
CREATE TABLE rules (
    id              INTEGER PRIMARY KEY,
    camera_id       INTEGER NOT NULL
                    REFERENCES cameras (id) ON DELETE CASCADE, -- kural kamerasız yaşayamaz
    rule_type       TEXT    NOT NULL CHECK (rule_type IN
                      ('zone_intrusion', 'safe_distance', 'ppe_violation')),
    -- Bölge silinirse ona bağlı kural anlamını yitirir; kural da silinir.
    -- Geçmiş olaylar etkilenmez: kuralın o anki hali events.rule_snapshot'ta saklıdır.
    zone_id         INTEGER REFERENCES zones (id) ON DELETE CASCADE,
    target_classes  TEXT    NOT NULL,  -- JSON dizi, ör. ["person"] veya ["forklift","truck"]
    params          TEXT    NOT NULL,  -- JSON nesne; şeması rule_type'a göre Pydantic ile doğrulanır
    severity        TEXT    NOT NULL DEFAULT 'warning',
    cooldown_s      INTEGER NOT NULL DEFAULT 120,
    announcement_id INTEGER REFERENCES announcement_messages (id) ON DELETE SET NULL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT    NOT NULL   -- ISO-8601 UTC
);

-- -------------------------------------------------------------------- olaylar
CREATE TABLE events (
    id            INTEGER PRIMARY KEY,
    occurred_at   TEXT    NOT NULL,   -- ISO-8601 UTC
    event_type    TEXT    NOT NULL CHECK (event_type IN ('violation', 'system')),
    -- Olay geçmişi kanıttır: kamera veya kural silinse de olay silinmez.
    camera_id     INTEGER REFERENCES cameras (id) ON DELETE SET NULL,
    rule_id       INTEGER REFERENCES rules (id) ON DELETE SET NULL,
    rule_snapshot TEXT,               -- JSON: olay anındaki kural adı/parametreleri
    details       TEXT,               -- JSON: KKD olaylarında model sürümü + gözlem penceresi dahil
    snapshot_path TEXT,               -- kanıt fotoğrafı (veri/goruntuler/ altında)
    status        TEXT    NOT NULL DEFAULT 'new'
                  CHECK (status IN ('new', 'reviewed', 'false_alarm')),
    note          TEXT,
    reviewed_at   TEXT                -- ISO-8601 UTC
);

-- docs/02-MIMARI.md §3'te belirtilen üç indeks:
CREATE INDEX idx_events_occurred_at     ON events (occurred_at);
CREATE INDEX idx_events_camera_occurred ON events (camera_id, occurred_at);
CREATE INDEX idx_events_status          ON events (status);

-- ------------------------------------------------------- KKD veri örnekleri
CREATE TABLE ppe_samples (
    id           INTEGER PRIMARY KEY,
    -- Eğitim verisi kameradan uzun yaşar; kamera silinince örnekler kalır.
    camera_id    INTEGER REFERENCES cameras (id) ON DELETE SET NULL,
    captured_at  TEXT NOT NULL,      -- ISO-8601 UTC
    crop_path    TEXT NOT NULL,
    helmet_label TEXT CHECK (helmet_label IN ('yes', 'no', 'unknown')), -- NULL = henüz etiketlenmedi
    vest_label   TEXT CHECK (vest_label   IN ('yes', 'no', 'unknown')), -- NULL = henüz etiketlenmedi
    source       TEXT NOT NULL CHECK (source IN ('scheduled', 'auto', 'feedback')),
    labeled_at   TEXT                -- ISO-8601 UTC
);
