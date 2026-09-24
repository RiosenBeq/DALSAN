# 05 - Teknoloji Kararları

> Bu dosyadaki bazı kararlar `09-BASITLESTIRME-KARARLARI.md` ile **değişti**;
> çelişki varsa 09 geçerlidir. Değişen ya da farklı uygulanan satırların yanında
> bugünkü karşılığı *italik* not olarak yazılıdır.

Seçim kriterleri (öncelik sırasıyla): stabilite · basitlik · geliştirme hızı ·
Claude Code uyumu · Mac + Windows · Docker · bakım · büyütülebilirlik.

"En modern" değil, "bu proje için en mantıklı."

## 1. Yığın

| Katman | Seçim | Neden | Elenen |
|---|---|---|---|
| Dil | **Python 3.12** | CV ekosisteminin tamamı burada; Claude Code'un en güçlü olduğu alan | - |
| API | **FastAPI + Pydantic v2** | Validasyon yerleşik, OpenAPI otomatik, async SSE doğal | Django (ağır), Flask (validasyon/async zayıf) |
| ORM | **SQLAlchemy 2.0 + Alembic** *(→ 09 #6: ORM yok; standart `sqlite3` + sürümlü betikler `backend/sema/NNN_*.sql`, `app/veritabani.py`)* | Standart; Alembic 1. günden | Raw SQL (migrasyon disiplini zorlaşır) |
| DB | **PostgreSQL 16 (Docker)** *(→ 09 #2: SQLite, tek dosya `veri/dalsan.db`)* | `timestamptz`, JSONB, iki süreçten eşzamanlı yazma, `pg_dump`, büyümeye açık | **SQLite** - 4 kamerada yeterdi ama analizör+API eşzamanlı yazıyor ve fabrika geneline çıkarken geçiş maliyeti şimdi ödenenden yüksek |
| Görüntü alma | **OpenCV (FFmpeg backend)**, RTSP over TCP | En az bağımlılık, yeterli | PyAV / GStreamer (esnek ama kurulum ağır) |
| Dedektör | **Karar: 1. hafta - bkz. ADR-002** *(kapandı: YOLOX, ONNX Runtime ile; `onnxruntime==1.30.0`, Intel Mac'te 1.23.2 - `backend/requirements.txt`)* | Ultralytics YOLO (hızlı ama AGPL) vs Apache-2.0 alternatifler (RF-DETR, YOLOX, D-FINE) | - |
| KKD sınıflandırıcı | **Hafif ImageNet ön eğitimli omurga** (MobileNetV3 / EfficientNet-B0 / ResNet-18 sınıfı), 3 sınıflı softmax × 2 *(model henüz eğitilmedi; ürüne yalnız ONNX dosyası girer, sözleşmesi `analiz/kkd_siniflandirici.py`)* | 4 kamerada hepsi fazlasıyla hızlı; seçim bakım kolaylığına göre | Büyük ViT (gereksiz), tek aşamalı dedektör (bkz. `04-KKD` Bölüm 2) |
| Takip + bölge | **`supervision`** (MIT) *(`supervision==0.25.1`; kullanılan yalnız ByteTrack - bölge içi testi saf `rules/geometri.py`'dedir, PolygonZone kullanılmaz)* | ByteTrack, PolygonZone; modelden bağımsız → ADR-002 kararını etkilemez | Kendi ByteTrack implementasyonu |
| Kalibrasyon | **OpenCV homografi**, 4 nokta *(uygulamada OpenCV kullanılmaz; hesap saf numpy)* | ~20 satır; `rules/kalibrasyon.py` içinde saf numpy | - |
| Frontend | **Vite + React + TS + Tailwind** *(→ 09 #3: Jinja2 şablonu + sade JavaScript, derleme adımı yok)* | Poligon editörü için React doğal; build çıktısı FastAPI'den servis edilir, runtime'da Node yok | Next.js (SSR gereksiz), HTMX+Jinja (editör zor) |
| Gerçek zamanlı | **SSE** (`sse-starlette`) *(`sse-starlette` kurulmadı; SSE FastAPI'nin `StreamingResponse`'uyla: `web/olaylar_web.py`)* | Tek yön; WebSocket bağlantı yönetimi gereksiz | WebSocket |
| Container | **Docker Compose** + NVIDIA Container Toolkit (prod) *(→ 09 #4: fabrikada tek servis / tek container, geliştirmede Docker yok; imaj yalnız CPU ONNX Runtime kurar, GPU bloğu `docker-compose.yml`'de kapalı)* | Üç servis, tek komut | Kubernetes |
| Test | **pytest** + httpx; **ruff** (lint+format) | Standart, hızlı | mypy (opsiyonel) |
| Log | **stdlib logging → JSON satır**, stdout, Docker rotasyonu *(uygulamada: ekran akışı (stderr) + `veri/loglar/sistem.log`; dosya uygulamanın kendisince 5 MB'ta döner, son 3 kopya - `app/loglama.py`)* | Ek bağımlılık yok | ELK / Loki |
| Config | **pydantic-settings + `.env`** *(pydantic-settings kurulmadı: `python-dotenv` + `app/ayarlar.py` → `Ayarlar`)* | Tip güvenli, tek kaynak | - |
| CI | **GitHub Actions: lint + test** *(uygulanmadı: lint + test iş akışı yok; `ruff` ve tam `pytest` hiçbir iş akışında koşmaz. Actions'ta yalnız `uygulama-uret.yml` - Windows/Mac paketini üretip açarak sınar - ve forklift eğitimi `forklift-egit.yml` / `forklift-egit-bacak.yml` var; sonuncusu yalnız `tests/test_forklift_modeli.py`'yi koşar)* | "Complex CI/CD" değil; deploy manuel script | Otomatik deploy pipeline |

## 2. Platform

| Ortam | Durum |
|---|---|
| **Prod - fabrika** | Ubuntu 22.04/24.04 LTS + NVIDIA GPU. Docker'da GPU erişimi güvenilir biçimde yalnızca Linux'ta. Windows Server + Docker Desktop teknik olarak mümkün ama 7x24 fabrika işletimi için önerilmez. *(Bugünkü Docker imajı yalnız CPU ONNX Runtime kurar; GPU için `onnxruntime-gpu`'lu ayrı imaj gerekir ve henüz yok. Sunucu donanımı docs/17 §16 S1'de açık.)* |
| **Dev - Mac (Apple Silicon)** | Docker'da GPU yok. Analizör CPU modunda (düşük fps) veya video dosyası kaynağıyla. İsteğe bağlı: analizör Docker dışında MPS ile. API + DB Docker'da. *(→ 09 #4: geliştirmede Docker yok; tek program Kontrol Paneli'nden doğrudan Python ile çalışır, tespit CPU'da - `CIKARIM_CIHAZI` yalnız `cpu` / `cuda` alır, MPS yolu yok.)* |
| **Dev - Windows** | Docker Desktop + WSL2 ile CUDA çalışır; yerel GPU varsa prod'a yakın test. *(→ 09 #4: geliştirmede Docker yok; kurulum yalnız CPU paketini kurar, CUDA için `onnxruntime-gpu` gerekir.)* |

## 3. Sunucu gereksinimi - 3-4 kamera için güncellendi

Teklif donanımı kapsam dışı bırakıyor; gereksinim 1. haftada DALSAN'a **yazılı** iletilir.

| Bileşen | 3-4 kamera (MVP) | Fabrika geneli (~30-40 kamera, Phase 3) |
|---|---|---|
| GPU | **NVIDIA ≥ 8 GB** (RTX 4060 / 4060 Ti / T4 sınıfı) | Çoklu GPU veya 2-3 analizör düğümü |
| CPU | ≥ 6 çekirdek | ≥ 24 çekirdek (RTSP decode CPU'yu yer) |
| RAM | ≥ 16 GB | ≥ 64 GB |
| Disk | ≥ 512 GB SSD | ≥ 4 TB + retention politikası |
| Ağ | Kamera VLAN'ı + anons altyapısına erişim, NTP | Ayrılmış kamera ağı |

**Performans bütçesi (MVP):** 4 kamera × 6 fps = **24 çıkarım/sn** + seyrek KKD
sınıflandırması. 640 px'de küçük/orta model tek 8 GB GPU'da rahat; ciddi başlık payı kalır.

**CPU-only:** kamera başına ~1-2 fps'e düşer. Bölge kuralı için sınırda, mesafe kuralı
için zayıf, **KKD için yetersiz** (zamansal oylama yeterli gözlem bulamaz). GPU şarttır.
*(Ölçüm - `AUDIT-OLCUM.md` §1.2, 4 çekirdekli CPU, 4 kamera, ONNX Runtime 1.19.2:
`yolox_tiny` kamera başına 6,0 fps (bütçenin %100'ü, makine doygun), `yolox_s` 2,4 fps
(%40). 23.09.2026'daki yeniden ölçümde bütçe `yolox_tiny` ile %100,1, `yolox_s` ile
%43,4 (`ILERLEME.md` «Hız ve CPU»). "~1-2 fps" `yolox_s` için yaklaşık doğru,
`yolox_tiny` için değil.)*

---

## 4. Mimari Karar Kayıtları (ADR)

### ADR-001 - Modular Monolith, iki süreç
**Durum:** Kabul → **09 #1 ile değişti:** tek program; analiz FastAPI içinde arka plan iş parçacığı olarak çalışır (`app/uygulama.py`, `analiz/supervizor.py`).
**Bağlam:** 3-4 kamera, tek operatör, tek sunucu.
**Karar:** Tek kod tabanı, tek DB, iki runtime süreci (api, analyzer). Broker yok.
**Sonuç:** Basit deploy ve teşhis. Yatay ölçekleme için ileride analizör bölümlendirmesi gerekir (bkz. `07-YOL-HARITASI.md` §3).

### ADR-002 - Dedektör modeli ve lisansı
**Durum:** **Kapandı - (B) uygulandı:** YOLOX (Apache-2.0), ONNX Runtime ile (`analiz/tespit.py`, `backend/requirements.txt`); operatör docs/17 §16 S2'nin varsayılanını ("Hayır; YOLOX") 23.09.2026'da kabul etti. *(İlk durum: AÇIK - 1. haftada kapatılacak.)*
**Bağlam:** Ultralytics YOLO en hızlı geliştirme yolu ama **AGPL-3.0**. Kapalı kaynak ticari teslimatta ya kaynak paylaşımı ya Ultralytics Enterprise lisansı gerekir. Teklif Bölüm 10 "üçüncü taraf lisans ücretleri"ni kapsam dışı bırakıyor → maliyet DALSAN'a ayrı kalem olarak gider veya müzakere gerekir.
**Seçenekler:** (A) Enterprise lisans (B) Apache-2.0 alternatif: RF-DETR, YOLOX, D-FINE
**Öneri:** **(B)** - ek maliyet ve müzakere getirmez.
**Etki izolasyonu:** Karar `Detector` arayüzü arkasında; kodun geri kalanını etkilemez. *(Kodda: `analiz/tespit.py` → `Tespitci` sınıfı.)*
**Not (ürün adı):** Seçilen dedektör kullanıcı arayüzünde **NextGen AI** adıyla görünür (Hızlı / İsabetli). Bu yalnızca EKRAN metnidir: dosya adları, indirme adresleri ve `.env` anahtarları değişmez. Görünen adı üreten tek yer `backend/app/analiz/model_adi.py`, Apache-2.0 atfı ise depo kökündeki `LICENSE-THIRD-PARTY` dosyasıdır.

### ADR-003 - İki aşamalı KKD (dedektör yerine sınıflandırıcı)
**Durum:** Kabul
**Bağlam:** Baret, kişi boyunun ~1/8'i. Tek aşamalı küçük nesne tespiti hem veri hem doğruluk açısından pahalı.
**Karar:** person crop → çok etiketli sınıflandırıcı. Gerekçe tablosu: `04-KKD-BARET-YELEK.md` §2.
**Sonuç:** Ucuz etiketleme, doğal `unknown`, kolay yeniden eğitim. Bedeli: baretin etrafında kutu çizilemez; kişi kutusu renklendirilir.

### ADR-004 - Üç durumlu KKD kararı
**Durum:** Kabul
**Karar:** `yes` / `no` / `unknown`. `unknown` asla olay üretmez.
**Gerekçe:** Yanlış alarm, kaçırılan ihlalden daha maliyetlidir (`00-PROJE-BAGLAMI.md`).

### ADR-005 - Redis / message broker yok
**Durum:** Kabul
**Karar:** Analizör → DB → SSE polling (1 sn).
**Gerekçe:** Tek operatör ekranı; polling yükü ölçülemez. Yükseltme yolu `LISTEN/NOTIFY` - yine ek altyapı yok.
**Not (bugün):** Analiz iş parçacığı SQLite'a yazar, `/olaylar/akis` saniyede bir sorar (`web/olaylar_web.py`). SQLite'ta `LISTEN/NOTIFY` yoktur; bu yükseltme yolu PostgreSQL'e geçişle açılır (09 "Ne kaybettik" #1).

### ADR-006 - PostgreSQL, SQLite değil
**Durum:** Kabul → **09 #2 ile değişti:** SQLite, tek dosya (`veri/dalsan.db`).
**Karar:** PostgreSQL 16.
**Gerekçe:** İki süreçten eşzamanlı yazma; `timestamptz`; fabrika geneli yayılımda kaçınılmaz. Maliyet: tek container.

### ADR-007 - `cameras.area` düz metin alan, `areas` tablosu değil
**Durum:** Kabul
**Bağlam:** Fabrika geneli yayılım hedefi var ama bugün 3-4 kamera.
**Karar:** `cameras.area` - indeksli metin alanı. Ayrı tablo, FK, CRUD ekranı **yok**.
**Gerekçe:** Bugünün ihtiyacı (olay filtreleme) karşılanır; yarının ihtiyacı (alan bazlı yetki, alan raporu) tek migrasyonla eklenir. "Geleceğe hazırlık ≠ bugün geliştirme."

### ADR-008 - Analizörün kamera kümesi tek fonksiyondan gelir
**Durum:** Kabul
**Karar:** `get_assigned_cameras()` - bugün "tüm aktif kameralar" döner. Bölümlendirme alanı (`analyzer_group`) **eklenmez**.
**Gerekçe:** Fabrika geneline çıkarken çoklu analizör düğümü gerekecek. O gün yapılacak iş: bu fonksiyonu değiştirmek + bir alan eklemek. Bugün alanı eklemek, kullanılmayan konfigürasyon demektir.
**Not (kodda):** Fonksiyonun adı `AnalizSupervizoru._atanmis_kameralar()` (`analiz/supervizor.py`); `enabled = 1` olan bütün kameraları döndürür.

### ADR-009 - Ham video kaydedilmez
**Durum:** Kabul
**Karar:** Yalnızca olay anı snapshot'ı saklanır; sürekli kayıt yok.
**Gerekçe:** NVR zaten kayıt yapıyor (mükerrer); disk maliyeti; KVKK'da veri minimizasyonu. Olay video klibi Phase 2'de değerlendirilir.
