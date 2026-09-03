-- 004_nesne_teshisi.sql
--
-- TEK YENİ TABLO. Bu betikte YALNIZCA "CREATE TABLE" vardır; hiçbir mevcut
-- tablo düşürülmez, yeniden kurulmaz, CHECK kısıtı değiştirilmez. 001, 002 ve
-- 003 dosyalarına dokunulmaz: kurulu sistemlerde çoktan uygulanmıştır.
-- Betikler BEGIN/COMMIT İÇERMEZ; sarmalamayı app/veritabani.py yapar.
--
-- ------------------------------------------------------------- ne işe yarar
--
-- Kullanıcı bir nesnenin fotoğraflarını yükleyince, sistem o nesnenin NE KADAR
-- TANINABİLİR olduğunu söyler ("kolay tanınır" / "düz renkli, kısıtlı" /
-- "zor tanınır"). Bu yargı uydurma değildir; nesnenin KENDİ fotoğraflarından
-- ölçülür (app/nesneler/teshis.py):
--
--   nokta       — fotoğraflardaki desen (ORB) anahtar noktası sayısının ortancası
--   tutarlilik  — her fotoğrafın DİĞER fotoğraflara benzerliği (0-1)
--
-- NEDEN SAKLANIYOR: ölçüm fotoğrafları diskten okuyup yeniden parmak izi
-- çıkarmayı gerektirir (ölçüldü: fotoğraf başına ~19 ms). 10 nesne × 8 fotoğraf
-- = 1,6 saniye; bu sayfa her ekleme/silme sonrası yeniden yüklendiği için
-- kullanıcı bunu bekleme olarak hisseder. Sonuç bu yüzden bir kez hesaplanıp
-- burada tutulur.
--
-- BAYATLAMA: `photo_key`, ölçümün HANGİ fotoğraflardan çıktığını yazar
-- (fotoğraf id'leri, sıralı, virgülle). Nesneye fotoğraf eklenir ya da
-- silinirse anahtar tutmaz ve teşhis kendiliğinden yeniden hesaplanır. Ayrı
-- bir "geçersiz kıl" adımı yoktur — unutulabilecek bir adım da yoktur.
--
-- KAPSAM SINIRI: bu tablo da 003 gibi CANLI ANALİZİ ETKİLEMEZ. Kural motoru
-- (rules/) ve canlı boru hattı bu tabloyu hiç okumaz.

CREATE TABLE library_object_diagnosis (
    object_id   INTEGER PRIMARY KEY
                REFERENCES library_objects (id) ON DELETE CASCADE, -- nesne silinince teşhis de gider
    photo_key   TEXT    NOT NULL,   -- ölçümün dayandığı fotoğraf id'leri: "3,7,9"
    keypoints   INTEGER NOT NULL,   -- desen anahtar noktası sayısının ortancası
    consistency REAL    NOT NULL,   -- fotoğrafların birbirini tanıma oranı (0-1)
    computed_at TEXT    NOT NULL    -- ISO-8601 UTC (app/zaman.py)
);
