# 05 — Teknoloji Kararları

Seçim kriterleri (öncelik sırasıyla): stabilite · basitlik · geliştirme hızı ·
Claude Code uyumu · Mac + Windows · Docker · bakım · büyütülebilirlik.

"En modern" değil, "bu proje için en mantıklı."

## 1. Yığın

| Katman | Seçim | Neden | Elenen |
|---|---|---|---|
| Dil | **Python 3.12** | CV ekosisteminin tamamı burada; Claude Code'un en güçlü olduğu alan | — |
| API | **FastAPI + Pydantic v2** | Validasyon yerleşik, OpenAPI otomatik, async SSE doğal | Django (ağır), Flask (validasyon/async zayıf) |
| ORM | **SQLAlchemy 2.0 + Alembic** | Standart; Alembic 1. günden | Raw SQL (migrasyon disiplini zorlaşır) |
| DB | **PostgreSQL 16 (Docker)** | `timestamptz`, JSONB, iki süreçten eşzamanlı yazma, `pg_dump`, büyümeye açık | **SQLite** — 4 kamerada yeterdi ama analizör+API eşzamanlı yazıyor ve fabrika geneline çıkarken geçiş maliyeti şimdi ödenenden yüksek |
| Görüntü alma | **OpenCV (FFmpeg backend)**, RTSP over TCP | En az bağımlılık, yeterli | PyAV / GStreamer (esnek ama kurulum ağır) |
| Dedektör | **Karar: 1. hafta — bkz. ADR-002** | Ultralytics YOLO (hızlı ama AGPL) vs Apache-2.0 alternatifler (RF-DETR, YOLOX, D-FINE) | — |
| KKD sınıflandırıcı | **Hafif ImageNet ön eğitimli omurga** (MobileNetV3 / EfficientNet-B0 / ResNet-18 sınıfı), 3 sınıflı softmax × 2 | 4 kamerada hepsi fazlasıyla hızlı; seçim bakım kolaylığına göre | Büyük ViT (gereksiz), tek aşamalı dedektör (bkz. `04-KKD` Bölüm 2) |
| Takip + bölge | **`supervision`** (MIT) | ByteTrack, PolygonZone; modelden bağımsız → ADR-002 kararını etkilemez | Kendi ByteTrack implementasyonu |
| Kalibrasyon | **OpenCV homografi**, 4 nokta | ~20 satır; `rules/calibration.py` içinde saf numpy | — |
| Frontend | **Vite + React + TS + Tailwind** | Poligon editörü için React doğal; build çıktısı FastAPI'den servis edilir, runtime'da Node yok | Next.js (SSR gereksiz), HTMX+Jinja (editör zor) |
| Gerçek zamanlı | **SSE** (`sse-starlette`) | Tek yön; WebSocket bağlantı yönetimi gereksiz | WebSocket |
| Container | **Docker Compose** + NVIDIA Container Toolkit (prod) | Üç servis, tek komut | Kubernetes |
| Test | **pytest** + httpx; **ruff** (lint+format) | Standart, hızlı | mypy (opsiyonel) |
| Log | **stdlib logging → JSON satır**, stdout, Docker rotasyonu | Ek bağımlılık yok | ELK / Loki |
| Config | **pydantic-settings + `.env`** | Tip güvenli, tek kaynak | — |
| CI | **GitHub Actions: lint + test** | "Complex CI/CD" değil; deploy manuel script | Otomatik deploy pipeline |

## 2. Platform

| Ortam | Durum |
|---|---|
| **Prod — fabrika** | Ubuntu 22.04/24.04 LTS + NVIDIA GPU. Docker'da GPU erişimi güvenilir biçimde yalnızca Linux'ta. Windows Server + Docker Desktop teknik olarak mümkün ama 7x24 fabrika işletimi için önerilmez. |
| **Dev — Mac (Apple Silicon)** | Docker'da GPU yok. Analizör CPU modunda (düşük fps) veya video dosyası kaynağıyla. İsteğe bağlı: analizör Docker dışında MPS ile. API + DB Docker'da. |
| **Dev — Windows** | Docker Desktop + WSL2 ile CUDA çalışır; yerel GPU varsa prod'a yakın test. |

## 3. Sunucu gereksinimi — 3-4 kamera için güncellendi

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

---

## 4. Mimari Karar Kayıtları (ADR)

### ADR-001 — Modular Monolith, iki süreç
**Durum:** Kabul
**Bağlam:** 3-4 kamera, tek operatör, tek sunucu.
**Karar:** Tek kod tabanı, tek DB, iki runtime süreci (api, analyzer). Broker yok.
**Sonuç:** Basit deploy ve teşhis. Yatay ölçekleme için ileride analizör bölümlendirmesi gerekir (bkz. `07-YOL-HARITASI.md` §3).

### ADR-002 — Dedektör modeli ve lisansı
**Durum:** **AÇIK — 1. haftada kapatılacak**
**Bağlam:** Ultralytics YOLO en hızlı geliştirme yolu ama **AGPL-3.0**. Kapalı kaynak ticari teslimatta ya kaynak paylaşımı ya Ultralytics Enterprise lisansı gerekir. Teklif Bölüm 10 "üçüncü taraf lisans ücretleri"ni kapsam dışı bırakıyor → maliyet DALSAN'a ayrı kalem olarak gider veya müzakere gerekir.
**Seçenekler:** (A) Enterprise lisans (B) Apache-2.0 alternatif: RF-DETR, YOLOX, D-FINE
**Öneri:** **(B)** — ek maliyet ve müzakere getirmez.
**Etki izolasyonu:** Karar `Detector` arayüzü arkasında; kodun geri kalanını etkilemez.
**Not (ürün adı):** Seçilen dedektör kullanıcı arayüzünde **NextGen AI** adıyla görünür (Hızlı / İsabetli). Bu yalnızca EKRAN metnidir: dosya adları, indirme adresleri ve `.env` anahtarları değişmez. Görünen adı üreten tek yer `backend/app/analiz/model_adi.py`, Apache-2.0 atfı ise depo kökündeki `LICENSE-THIRD-PARTY` dosyasıdır.

### ADR-003 — İki aşamalı KKD (dedektör yerine sınıflandırıcı)
**Durum:** Kabul
**Bağlam:** Baret, kişi boyunun ~1/8'i. Tek aşamalı küçük nesne tespiti hem veri hem doğruluk açısından pahalı.
**Karar:** person crop → çok etiketli sınıflandırıcı. Gerekçe tablosu: `04-KKD-BARET-YELEK.md` §2.
**Sonuç:** Ucuz etiketleme, doğal `unknown`, kolay yeniden eğitim. Bedeli: baretin etrafında kutu çizilemez; kişi kutusu renklendirilir.

### ADR-004 — Üç durumlu KKD kararı
**Durum:** Kabul
**Karar:** `yes` / `no` / `unknown`. `unknown` asla olay üretmez.
**Gerekçe:** Yanlış alarm, kaçırılan ihlalden daha maliyetlidir (`00-PROJE-BAGLAMI.md`).

### ADR-005 — Redis / message broker yok
**Durum:** Kabul
**Karar:** Analizör → DB → SSE polling (1 sn).
**Gerekçe:** Tek operatör ekranı; polling yükü ölçülemez. Yükseltme yolu `LISTEN/NOTIFY` — yine ek altyapı yok.

### ADR-006 — PostgreSQL, SQLite değil
**Durum:** Kabul
**Karar:** PostgreSQL 16.
**Gerekçe:** İki süreçten eşzamanlı yazma; `timestamptz`; fabrika geneli yayılımda kaçınılmaz. Maliyet: tek container.

### ADR-007 — `cameras.area` düz metin alan, `areas` tablosu değil
**Durum:** Kabul
**Bağlam:** Fabrika geneli yayılım hedefi var ama bugün 3-4 kamera.
**Karar:** `cameras.area` — indeksli metin alanı. Ayrı tablo, FK, CRUD ekranı **yok**.
**Gerekçe:** Bugünün ihtiyacı (olay filtreleme) karşılanır; yarının ihtiyacı (alan bazlı yetki, alan raporu) tek migrasyonla eklenir. "Geleceğe hazırlık ≠ bugün geliştirme."

### ADR-008 — Analizörün kamera kümesi tek fonksiyondan gelir
**Durum:** Kabul
**Karar:** `get_assigned_cameras()` — bugün "tüm aktif kameralar" döner. Bölümlendirme alanı (`analyzer_group`) **eklenmez**.
**Gerekçe:** Fabrika geneline çıkarken çoklu analizör düğümü gerekecek. O gün yapılacak iş: bu fonksiyonu değiştirmek + bir alan eklemek. Bugün alanı eklemek, kullanılmayan konfigürasyon demektir.

### ADR-009 — Ham video kaydedilmez
**Durum:** Kabul
**Karar:** Yalnızca olay anı snapshot'ı saklanır; sürekli kayıt yok.
**Gerekçe:** NVR zaten kayıt yapıyor (mükerrer); disk maliyeti; KVKK'da veri minimizasyonu. Olay video klibi Phase 2'de değerlendirilir.
