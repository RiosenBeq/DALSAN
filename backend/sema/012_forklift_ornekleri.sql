-- 012_forklift_ornekleri.sql (operatör isteği 24.09.2026)
--
-- Betik BEGIN/COMMIT içermez; sarmalamayı app/veritabani.py yapar.
--
-- Forklift modelini fabrikanın kendi görüntüsüyle eğitmek için sahadan kare
-- toplama (app/egitim/forklift_verisi.py). Açık veriyle (LOCO) iki tam eğitim
-- kapılardan geçemedi; çare hedef ortamın kendisidir. KKD veri toplamasıyla
-- aynı düzen: kapı KAPALI doğar, açmak onay ister, örnekleme her kareden önce
-- kapıyı okur. Kareler yalnız bu bilgisayarda durur; eğitim ürün dışında,
-- kapalı bir bilgisayarda yapılır (CLAUDE.md, forklift eğitimi istisnası).

-- ------------------------------------------------------------ toplama kapısı
-- Tek satır (id = 1). .env'de DEĞİL: çalışırken açılıp kapanır.
CREATE TABLE forklift_collection_gate (
    id         INTEGER PRIMARY KEY,   -- her zaman 1
    enabled    INTEGER NOT NULL DEFAULT 0,
    changed_at TEXT,                  -- ISO-8601 UTC; NULL = hiç değiştirilmedi
    note       TEXT                   -- açarken verilen onay metni
);
INSERT INTO forklift_collection_gate (id, enabled) VALUES (1, 0);

-- ------------------------------------------------------------ kareler
-- Tam kare (uzun kenarı en çok 1280 piksel). Kişi de görünebilir: bu yüzden
-- yalnız kapı açıkken toplanır, etiketsizleri saklama süresi dolunca silinir.
CREATE TABLE forklift_samples (
    id          INTEGER PRIMARY KEY,
    camera_id   INTEGER REFERENCES cameras(id) ON DELETE SET NULL,
    captured_at TEXT    NOT NULL,              -- ISO-8601 UTC
    frame_path  TEXT    NOT NULL,              -- görüntü klasörüne göre
    width       INTEGER NOT NULL,
    height      INTEGER NOT NULL,
    -- Analizin o karedeki araç ve forklift kutuları (JSON listesi:
    -- {"kutu": [x1, y1, x2, y2], "sinif": "truck", "puan": 0.61}); etiketçiye öneri.
    proposals   TEXT    NOT NULL DEFAULT '[]',
    -- Etiket (JSON listesi: {"kutu": [...], "sinif": "forklift" | "pallet_jack"}).
    -- Boş liste = karede forklift yok. NULL = etiketlenmedi.
    labels      TEXT,
    labeled_at  TEXT
);
CREATE INDEX idx_forklift_samples_labeled ON forklift_samples (labeled_at, captured_at);

-- İmha kaydı: silinen etiketsiz forklift karesi sayısı (docs/17 §10.1).
ALTER TABLE purge_log ADD COLUMN forklift_samples_deleted INTEGER NOT NULL DEFAULT 0;
