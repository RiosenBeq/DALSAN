# İlerleme

## Platform uyumu + Docker (26.08.2026)

- **Windows uyumu düzeltildi:** anons sesi (PowerShell SoundPlayer — `afplay`/`aplay` Windows'ta yok), kamera arka ucu (DirectShow), saat dilimi veritabanı (`tzdata` bağımlılığı).
- **Docker desteği:** üç proje için de Dockerfile + docker-compose. Veri ve ayarlar container dışında (silinse de kaybolmaz), sağlık kontrolü ve otomatik yeniden başlatma var; GPU ve ses kartı blokları Linux için hazır ve yorumlu.
- Model dosyası yoksa imaj derlemesi **anlaşılır bir mesajla durur** — modelsiz, hiçbir şey tespit etmeyen sessiz container tuzağı kapatıldı.
- **NASIL-CALISIR.md** yazıldı: sistemin işleyişi, Mac/Windows/Docker kurulumu, hangi ortamda neyin çalıştığını gösteren dürüst tablo, sorun giderme ve yedekleme.
- Docker bu makinede kurulu olmadığı için imaj derlemesi **denenemedi**; Dockerfile'lar statik olarak doğrulandı.

## Adım 2-7 + altyapılar — Sistem uçtan uca çalışır durumda (26.08.2026)

- **Kamera katmanı:** RTSP (TCP) / video dosyası kaynağı, "son kare" deseni, üstel beklemeli otomatik yeniden bağlanma, çevrimiçi/çevrimdışı takibi ve sistem olayları. Kamera CRUD + 1 sn'de yenilenen canlı önizleme (tespit kutuları çizili).
- **Tespit + takip:** YOLOX (Apache-2.0, ADR-002) ONNX Runtime ile — torch gerekmez; `models/indir.sh` modelleri indirir. ByteTrack (supervision) ile kalıcı takip ID. Forklift, saha verisiyle ince ayara kadar araç sınıfı üzerinden görünür (R1).
- **Kural motoru (`rules/`, saf):** üç kural tipi eksiksiz — bölge ihlali (inside/outside + kalış), güvenli mesafe (homografi + hareket koşulu + ardışık kare; kalibrasyonsuz kamerada bilerek pasif), KKD (üç durum + zamansal oylama; **belirsiz asla olay üretmez**). Cooldown ortak filtre; restart'sız konfig yayılımı durumu korur.
- **Olaylar:** kanıt fotoğrafı önce/DB sonra, rule_snapshot, SSE canlı uyarı paneli, filtreli liste, olay durumu (Yeni/İncelendi/Yanlış alarm + not), CSV dışa aktarma, korumalı fotoğraf servisi.
- **Kalibrasyon:** görüntüde 4 nokta tıkla + metre gir → homografi (saf numpy); arayüzde "kalibrasyon bekleniyor" rozetleri.
- **Anons:** Null / ses kartı (afplay-aplay) / HTTP adaptörleri + ekrandan bağımsız, daha uzun anons cooldown'u. Somut sistem bilgisi bekleniyor (R3).
- **KKD altyapısı:** KKD bölgelerinden saatlik limitle otomatik crop toplama + uygulama içi etiketleme sayfası (Var/Yok/Belirsiz). Model 9. adımda eğitilecek; o zamana dek KKD kuralı olay üretmez (belirsiz), veri biriktirir.
- **Güvenlik/işletim:** tek şifreli oturum (imzalı çerez), RTSP maskeleme, günlük retention + disk uyarısı, tek tıkla veritabanı yedeği.
- 92 test yeşil (kural motoru + web + entegrasyon), ruff temiz; gerçek görüntüyle uçtan uca doğrulandı (tespit → olay + kanıt fotoğrafı).
- Ayrıca: Kontrol Paneli'nin Mac'te açılmama sorunu çözüldü (çalıştırma izni + karantina + Python 3.12/tkinter).


## Adım 1 — Proje iskeleti + veritabanı + ana sayfa (26.08.2026)

- backend/ iskeleti kuruldu: .env'den okunan tek ayar kaynağı (ayarlar.py), SQLite bağlantısı (yabancı anahtar + WAL + busy_timeout) ve sürümlü şema düzeni (sema/001_ilk.sql → 7 tablo + 5 anons mesajı seed).
- Zaman yönetimi tek yerde (zaman.py: UTC sakla, İstanbul göster), JSON satır log (loglama.py → ekran + veri/loglar/sistem.log), tiplenmiş hatalar ve merkezi hata yakalayıcı (hatalar.py) eklendi.
- Teşhis ana sayfası hazır: şema sürümü, tablo listesi, maskeli aktif ayarlar, disk durumu ve "Henüz kamera eklenmedi".
- rules/ klasörü boş açıldı; saflık kuralı tests/rules/test_saflik.py ile korunuyor (doğrudan, dinamik ve dolaylı yasaklı import'lar testi kırmızı yapar).
- 30 test yeşil, ruff temiz; sıradaki iş: Adım 2 — kamera ekleme + görüntü alma.
