-- 008_kkd_veri.sql - Faz 3 (docs/17 §8.3, §5.7-5.8). YALNIZ ADD COLUMN: tablo
-- yeniden kurulmaz, yabancı anahtar kapatılmaz, göç öncesi yedek gerekmez.
--
-- ppe_samples: örnek alınırken kişinin kutu yüksekliği ve kırpığın netliği
-- (Laplacian varyansı, analiz/kkd_siniflandirici.netlik_olc). Veri setinde ve
-- değerlendirmede kırılım olurlar. Eski örneklerde NULL = ölçülmedi.
ALTER TABLE ppe_samples ADD COLUMN person_height_px INTEGER;
ALTER TABLE ppe_samples ADD COLUMN sharpness        REAL;
-- Etiketçinin işaretlediği zor örnek kodu (white_cap, reflective_jacket,
-- night_glare, backpack, raincoat, driver_cab). Kodların tek kaynağı
-- app/egitim/veri_seti.ZOR_ORNEKLER; CHECK bilerek yok (S22: yeni kod tablo
-- yeniden kurmayı gerektirmesin).
ALTER TABLE ppe_samples ADD COLUMN hard_case        TEXT;

-- KKD anons kapısından geçen model sürümü (dosya adı + sha256[:12]); NULL = hiç
-- onaylanmadı. params'a konmaz: params kural imzasına girer, cooldown'u ve
-- pencereleri sıfırlardı (rules/motor.py). Süpervizör yüklü modelin sürümünü
-- bununla karşılaştırır; farklıysa kural gölgeye döner (Faz 3d).
ALTER TABLE rules ADD COLUMN approved_model_version TEXT;
