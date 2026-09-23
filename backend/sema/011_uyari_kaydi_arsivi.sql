-- 011_uyari_kaydi_arsivi.sql (operatör isteği 23.09.2026)
--
-- YALNIZ "ALTER TABLE ... ADD COLUMN". Betik BEGIN/COMMIT içermez; sarmalamayı
-- app/veritabani.py yapar.
--
-- Uyarı kayıtları (alert_deliveries) UYARI_KAYDI_ARSIV_GUN günde bir masaüstüne
-- CSV olarak yazılır ve SONRA silinir (olaylar/uyari_arsivi.py). İmha kaydı
-- kaç satırın silindiğini ve nereye aktarıldığını tutar; kişisel veri yoktur.
ALTER TABLE purge_log ADD COLUMN alerts_archived INTEGER NOT NULL DEFAULT 0;
ALTER TABLE purge_log ADD COLUMN alert_archive_file TEXT;  -- yazılan CSV'nin tam yolu; yoksa NULL
