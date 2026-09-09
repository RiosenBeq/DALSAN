-- 005_arac_hizi_kurali.sql
--
-- DÖRDÜNCÜ KURAL TİPİ: 'vehicle_speed' (araç hız sınırı).
-- docs/07-YOL-HARITASI.md #15'te ertelenmiş olan iş; erteleme nedeni burada
-- çözülüyor.
--
-- ----------------------------------------------------- neden bu betik özel
--
-- `rules.rule_type` bir CHECK kısıtıyla ÜÇ tipe kapalıydı. SQLite'ta bir CHECK
-- kısıtını değiştirmenin tek yolu tabloyu yeniden kurmaktır: yeni tablo +
-- kopyala + eskiyi bırak. Bu betik, depodaki DİĞER TÜM betiklerin aksine
-- mevcut bir tabloyu yeniden kurar.
--
-- TEHLİKE (ölçülerek doğrulandı): `DROP TABLE rules`, yabancı anahtar zorlaması
-- AÇIKKEN `events.rule_id ... ON DELETE SET NULL` eylemini tetikler ve TÜM olay
-- geçmişinin kural bağlantısı sessizce silinir. Ölçüm:
--
--     ONCE  : [{'id': 1, 'rule_id': 1}, {'id': 2, 'rule_id': 2}]
--     SONRA : [{'id': 1, 'rule_id': None}, {'id': 2, 'rule_id': None}]
--
-- ÇÖZÜM: aşağıdaki işaret satırı. app/veritabani.py bu satırı görünce betiği
-- çalıştırmadan ÖNCE `PRAGMA foreign_keys = OFF` verir, sonra geri açar ve
-- `PRAGMA foreign_key_check` ile bağlantıların sağlam kaldığını DOĞRULAR.
-- PRAGMA'nın betiğin içine yazılamamasının sebebi: bu PRAGMA bir işlemin
-- İÇİNDE etkisizdir, betikler ise tek transaction içinde çalışır.
--
-- Atomiklik bozulmaz: betik + sürüm kaydı yine tek transaction'dadır.
--
-- DALSAN-SEMA: YABANCI-ANAHTAR-KAPALI
--
-- ------------------------------------------------------- ne işe yarıyor
--
-- Soru: "forklift fabrika içinde hız sınırını aştı mı?"
-- Hız verisi zaten hesaplanıyordu (rules/motor.py, kalibre kamerada
-- Tespit.hiz_mps) ama hiçbir kural onu okumuyordu. Karar mantığı
-- app/rules/hiz.py içindedir; bu betik yalnızca yeni tipin veritabanına
-- yazılabilmesini sağlar.
--
-- Betikler BEGIN/COMMIT İÇERMEZ; sarmalamayı app/veritabani.py yapar.

-- Yeni tablo, 001'deki `rules` ile SÜTUN SÜTUN aynıdır; tek fark rule_type
-- CHECK listesine 'vehicle_speed' eklenmesidir. shadow_mode 002'de ALTER ile
-- eklenmişti; burada tablonun asıl tanımına giriyor.
CREATE TABLE rules_yeni (
    id              INTEGER PRIMARY KEY,
    camera_id       INTEGER NOT NULL
                    REFERENCES cameras (id) ON DELETE CASCADE, -- kural kamerasız yaşayamaz
    rule_type       TEXT    NOT NULL CHECK (rule_type IN
                      ('zone_intrusion', 'safe_distance', 'ppe_violation', 'vehicle_speed')),
    -- Bölge silinirse ona bağlı kural anlamını yitirir; kural da silinir.
    -- Geçmiş olaylar etkilenmez: kuralın o anki hali events.rule_snapshot'ta saklıdır.
    zone_id         INTEGER REFERENCES zones (id) ON DELETE CASCADE,
    target_classes  TEXT    NOT NULL,  -- JSON dizi, ör. ["person"] veya ["forklift","truck"]
    params          TEXT    NOT NULL,  -- JSON nesne; şeması rule_type'a göre Pydantic ile doğrulanır
    severity        TEXT    NOT NULL DEFAULT 'warning',
    cooldown_s      INTEGER NOT NULL DEFAULT 120,
    announcement_id INTEGER REFERENCES announcement_messages (id) ON DELETE SET NULL,
    enabled         INTEGER NOT NULL DEFAULT 1,
    updated_at      TEXT    NOT NULL,  -- ISO-8601 UTC
    shadow_mode     INTEGER NOT NULL DEFAULT 0
);

-- Sütunlar TEK TEK yazılır. "INSERT INTO ... SELECT *" yazılsaydı, ileride
-- 002 gibi bir ALTER sütun eklediğinde sıra kayar ve veri sessizce yanlış
-- sütuna girerdi.
INSERT INTO rules_yeni (
    id, camera_id, rule_type, zone_id, target_classes, params,
    severity, cooldown_s, announcement_id, enabled, updated_at, shadow_mode
)
SELECT
    id, camera_id, rule_type, zone_id, target_classes, params,
    severity, cooldown_s, announcement_id, enabled, updated_at, shadow_mode
FROM rules;

DROP TABLE rules;

ALTER TABLE rules_yeni RENAME TO rules;
