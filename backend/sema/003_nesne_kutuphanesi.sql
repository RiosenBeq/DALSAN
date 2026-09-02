-- 003_nesne_kutuphanesi.sql
--
-- İKİ YENİ TABLO. Bu betikte YALNIZCA "CREATE TABLE" ve "CREATE INDEX" vardır;
-- hiçbir mevcut tablo düşürülmez, yeniden kurulmaz, CHECK kısıtı değiştirilmez.
-- 001 ve 002 dosyalarına dokunulmaz: kurulu sistemlerde çoktan uygulanmıştır.
-- Betikler BEGIN/COMMIT İÇERMEZ; sarmalamayı app/veritabani.py yapar.
-- (Gerekçenin tamamı 002_hoparlor_bolgeleri_ve_golge_mod.sql başındadır.)
--
-- --------------------------------------------------------- nesne kütüphanesi
--
-- NE İŞE YARAR: kullanıcı, sistemin tanımadığı KENDİ nesnesini (belirli bir
-- pano, tüp, kalıp, makine…) fotoğrafla tanıtır; sonra bir fotoğraf yükleyip
-- "bu karede o nesne var mı" diye sordurur.
--
-- KAPSAM SINIRI — BU TABLOLAR CANLI ANALİZİ ETKİLEMEZ: burada tanıtılan nesne
-- kameralarda ARANMAZ. Kural motoru (rules/) bu tabloları hiç okumaz; canlı
-- boru hattı da okumaz. Canlıda arama ayrı bir iştir (docs/07-YOL-HARITASI.md).
--
-- Parmak izleri (renk histogramı + desen tanımlayıcıları) VERİTABANINDA
-- TUTULMAZ: her açılışta fotoğraflardan yeniden hesaplanır. Kütüphane küçüktür
-- (nesne başına 3-8 fotoğraf), hesap hızlıdır ve ikili veriyi SQLite'ta
-- saklamak yedekleme dosyasını gereksiz büyütürdü.

CREATE TABLE library_objects (
    id          INTEGER PRIMARY KEY,
    name        TEXT NOT NULL,                 -- kullanıcının verdiği ad, ekranda görünür
    description TEXT NOT NULL DEFAULT '',      -- serbest not: "3. holdeki kırmızı pano"
    created_at  TEXT NOT NULL                  -- ISO-8601 UTC (app/zaman.py)
);

-- Aynı adla iki nesne olmasın: tarama sonucunda hangi nesnenin bulunduğu
-- ekranda ADIYLA yazılır; iki "Yangın tüpü" satırı raporu okunamaz yapardı.
CREATE UNIQUE INDEX idx_library_objects_name ON library_objects (name);

CREATE TABLE library_object_photos (
    id        INTEGER PRIMARY KEY,
    object_id INTEGER NOT NULL
              REFERENCES library_objects (id) ON DELETE CASCADE, -- nesne silinince fotoğraf kaydı da gider
    file      TEXT    NOT NULL,                -- veri/nesneler/ altındaki dosya ADI (yol değil)
    added_at  TEXT    NOT NULL                 -- ISO-8601 UTC
);

CREATE INDEX idx_library_object_photos_object ON library_object_photos (object_id);
