-- 009_uyari_kanallari.sql (Faz 4, docs/17 §7, §8; K22)
--
-- YALNIZ "ALTER TABLE ... ADD COLUMN" ve "CREATE". Hiçbir tablo yeniden
-- kurulmaz; yabancı anahtar kapatılmaz (bkz. 002'nin başındaki gerekçe).
-- Betik BEGIN/COMMIT içermez; sarmalamayı app/veritabani.py yapar.

-- ------------------------------------------------------------ uyarı kanalları
--
-- Kanal yapılandırmasının TEK yeri speaker_zones'dur (K22): bölüm başına bir
-- ya da birkaç satır; `area` boş satır "Tüm fabrika"dır ve bölümünde kanal
-- olmayan olayın geri düşüşüdür. Eskiden .env'deki ANONS / ANONS_SES_CIHAZI /
-- ANONS_HTTP_ADRESI de kanal tanımlıyordu; onlar 009'dan sonraki ilk açılışta
-- Python ile bir kez "Tüm fabrika" satırına aktarılır (olaylar/kanallar.py;
-- .env'i SQL okuyamaz).
--
-- Mevcut satırlar HTTP satırıdır (002): DEFAULT 'http' onları doğru sınıflar.
ALTER TABLE speaker_zones ADD COLUMN kind TEXT NOT NULL DEFAULT 'http';  -- http | ses_karti
-- ses_karti: hedef ses çıkışının (sink) adı. Linux'ta boş bırakılamaz (Python
-- doğrular, docs/17 §7.2 R37); boş değer yalnız aktarılmış eski kayıtta kalır
-- ve sağlıkta "bilinmiyor" sayılır, asla "bağlı" değil.
ALTER TABLE speaker_zones ADD COLUMN device TEXT NOT NULL DEFAULT '';
-- Kanal sağlığı (docs/17 §7.4): ok | down | unknown; NULL = henüz yoklanmadı.
-- updated_at'e DOKUNULMAZ: süpervizör yapılandırma damgası her yoklamada
-- yeniden yüklenmesin.
ALTER TABLE speaker_zones ADD COLUMN health TEXT;
ALTER TABLE speaker_zones ADD COLUMN health_changed_at TEXT;

-- ------------------------------------------------------------ teslim kaydı
--
-- Her uyarı denemesinin izi (docs/17 §7.3-10; docs/07 #16): hangi olay, hangi
-- kanal, sonuç ve yazılım gecikmesi. "Anons çaldı mı" sorusunun cevabı ve
-- uyarı garantisinin (§7.4) ölçüsü buradadır.
CREATE TABLE alert_deliveries (
    id                INTEGER PRIMARY KEY,
    -- NULL = olay satırı YAZILAMADI ama uyarı yine gönderildi (fail-safe,
    -- docs/17 §3.5) ya da test sesi. Bu satırları bakım queued_at'e göre siler.
    event_id          INTEGER REFERENCES events (id) ON DELETE CASCADE,
    -- NULL YALNIZ test sesinde (stage='test'); fail-safe satırında kod doludur.
    event_code        TEXT,
    speaker_zone_id   INTEGER REFERENCES speaker_zones (id) ON DELETE SET NULL,
    channel           TEXT    NOT NULL,  -- ekran | ses_karti | http
    stage             TEXT    NOT NULL,  -- acildi | hatirlatma | kapandi | test
    -- ok | failed | shadow | stale | preempted | fallback | no_listener |
    -- suppressed_cooldown
    result            TEXT    NOT NULL,
    detail            TEXT,              -- MASKELİ: adres ve şifre yazılmaz (R18)
    queued_at         TEXT    NOT NULL,  -- ISO-8601 UTC
    started_at        TEXT,
    finished_at       TEXT,
    frame_to_start_ms INTEGER            -- kare yakalama → çalıcı/istek başlangıcı (yalnız YAZILIM)
);
CREATE INDEX idx_alert_deliveries_event  ON alert_deliveries (event_id);
CREATE INDEX idx_alert_deliveries_queued ON alert_deliveries (queued_at);
