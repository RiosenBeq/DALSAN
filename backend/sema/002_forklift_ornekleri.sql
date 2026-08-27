-- 002_forklift_ornekleri.sql — Forklift ince ayarı için saha karesi toplama (docs/08 R1).
--
-- Hazır COCO modellerinde 'forklift' sınıfı yoktur; forklift 'truck'/'car' olarak
-- görünür. İnce ayar için sahadan 300-800 etiketli TAM KARE gerekir. Sistem, araç
-- tespit edilen karelerden saatlik limitle örnekler; kullanıcı /forklift sayfasında
-- her aday kutuyu "Forklift / Değil / Belirsiz" olarak etiketler.
--
-- KKD örneklerinden farkı: kırpık değil TAM kare saklanır (dedektör ince ayarı
-- tam kare + kutu ister) ve tek etiket vardır.

CREATE TABLE forklift_samples (
    id          INTEGER PRIMARY KEY,
    -- Eğitim verisi kameradan uzun yaşar; kamera silinince örnekler kalır.
    camera_id   INTEGER REFERENCES cameras (id) ON DELETE SET NULL,
    captured_at TEXT NOT NULL,       -- ISO-8601 UTC
    frame_path  TEXT NOT NULL,       -- tam kare JPEG (veri/goruntuler/forklift-ornekler/)
    bbox        TEXT NOT NULL,       -- JSON [x1,y1,x2,y2] normalize (0-1): aday araç kutusu
    label       TEXT CHECK (label IN ('yes', 'no', 'unknown')), -- forklift mi? NULL = etiketlenmedi
    source      TEXT NOT NULL DEFAULT 'auto' CHECK (source IN ('auto', 'manual')),
    labeled_at  TEXT                 -- ISO-8601 UTC
);
