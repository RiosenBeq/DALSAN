# İlerleme

## Adım 1 — Proje iskeleti + veritabanı + ana sayfa (26.08.2026)

- backend/ iskeleti kuruldu: .env'den okunan tek ayar kaynağı (ayarlar.py), SQLite bağlantısı (yabancı anahtar + WAL + busy_timeout) ve sürümlü şema düzeni (sema/001_ilk.sql → 7 tablo + 5 anons mesajı seed).
- Zaman yönetimi tek yerde (zaman.py: UTC sakla, İstanbul göster), JSON satır log (loglama.py → ekran + veri/loglar/sistem.log), tiplenmiş hatalar ve merkezi hata yakalayıcı (hatalar.py) eklendi.
- Teşhis ana sayfası hazır: şema sürümü, tablo listesi, maskeli aktif ayarlar, disk durumu ve "Henüz kamera eklenmedi".
- rules/ klasörü boş açıldı; saflık kuralı tests/rules/test_saflik.py ile korunuyor (doğrudan, dinamik ve dolaylı yasaklı import'lar testi kırmızı yapar).
- 30 test yeşil, ruff temiz; sıradaki iş: Adım 2 — kamera ekleme + görüntü alma.
