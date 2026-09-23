-- 010_kvkk_izleri.sql (Faz 5, docs/17 §8.3, §10)
--
-- YALNIZ "ALTER TABLE ... ADD COLUMN" ve "CREATE". Hiçbir tablo yeniden
-- kurulmaz; yabancı anahtar kapatılmaz (bkz. 002'nin başındaki gerekçe).
-- Betik BEGIN/COMMIT içermez; sarmalamayı app/veritabani.py yapar.

-- ------------------------------------------------------------ olay dondurma
--
-- Hukuki süreçte yalnız ilgili kayıt saklanır (Kurul kararı 8770): dondurulan
-- olay ve kanıt fotoğrafı saklama süresi dolsa da bakımda silinmez. Dondurmayı
-- ve çözmeyi yönetici şifresinin sahibi yapar (S5 varsayılanı); her değişiklik
-- access_log'a düşer.
ALTER TABLE events ADD COLUMN hold INTEGER NOT NULL DEFAULT 0;  -- 1 = saklama temizliğinden muaf
ALTER TABLE events ADD COLUMN hold_reason TEXT;

-- ------------------------------------------------------------ imha kaydı
--
-- Her bakım koşusu bir satır yazar (Silme Yönetmeliği: periyodik imha, kaydı
-- en az 3 yıl). Kişisel veri İÇERMEZ: yalnız sayılar ve o anki saklama gün
-- sayıları. Bakım bu tabloyu silmez.
CREATE TABLE purge_log (
    id              INTEGER PRIMARY KEY,
    ran_at          TEXT    NOT NULL,  -- ISO-8601 UTC
    events_deleted  INTEGER NOT NULL,
    photos_deleted  INTEGER NOT NULL,
    samples_deleted INTEGER NOT NULL,
    held_skipped    INTEGER NOT NULL,  -- süresi dolduğu halde dondurulduğu için silinmeyen olay
    policy          TEXT    NOT NULL   -- JSON: o anki saklama gün sayıları
);

-- ------------------------------------------------------------ erişim izi
--
-- KVKK m.12 denetim izi: kanıt görüntüleme, KKD kırpığı, dışa aktarım, ayar /
-- kural / dondurma değişikliği ve KKD toplama kapısı. Tek şifreli sistemde
-- "kim" istemci adresidir. Şifre, çerez ve ayar DEĞERİ yazılmaz. `target`
-- yabancı anahtar DEĞİLDİR: olay silinse de iz kalır. Bakım bu tabloyu silmez.
CREATE TABLE access_log (
    id     INTEGER PRIMARY KEY,
    at     TEXT NOT NULL,  -- ISO-8601 UTC
    client TEXT NOT NULL,
    -- view_snapshot | view_ppe_crop | export_csv | export_dataset |
    -- settings_change | rule_change | hold_change | ppe_collection_gate
    action TEXT NOT NULL,
    target TEXT
);
CREATE INDEX idx_access_log_at ON access_log (at);

-- ------------------------------------------------------------ mahremiyet kontrolü
--
-- Kameranın görüş alanında tuvalet, soyunma odası, duş, mescit, dinlenme ya da
-- emzirme odası olmadığı kurulumda elle doğrulanır (docs/17 §10.1, Kurul
-- 2022/797). NULL = henüz doğrulanmadı; kurulum listesi kırmızı değil ama
-- "sıradaki adım" gösterir. docs/17 §8.3 taslağına bu madde için eklendi.
ALTER TABLE cameras ADD COLUMN privacy_checked_at TEXT;
