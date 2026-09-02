# 02 — Mimari ve Veri Modeli

## 1. Prensip: Modular Monolith, iki runtime süreci

Tek repo, tek Python paketi (`app/`), tek veritabanı. Çalışma zamanında iki süreç:

- **`api`** — FastAPI + derlenmiş frontend (statik). Konfigürasyon CRUD, olay sorguları, SSE.
- **`analyzer`** — Görüntü alma, tespit, takip, KKD sınıflandırma, kural değerlendirme, olay yazma, anons.

Bu bir microservice ayrımı **değildir**: aynı kod tabanı, aynı modeller, aynı `settings`.
Ayrı süreç olmasının tek nedeni GPU çıkarımının API'yi bloklamaması ve analizörün
API'den bağımsız yeniden başlatılabilmesidir. Aralarında mesaj kuyruğu yok;
tek paylaşılan şey PostgreSQL.

```
Kameralar / NVR ──RTSP──▶ ┌───────────────────── analyzer ─────────────────────┐
       (3-4 adet)         │ CameraSource (kamera başına thread, "son kare")     │
                          │  → FrameSampler (5-8 fps)                           │
                          │  → Detector (paylaşımlı model, batch)               │
                          │  → Tracker (kamera başına ByteTrack)                │
                          │  → PpeClassifier (yalnızca KKD bölgesindeki person) │
                          │  → RuleEngine [rules/ — SAF, CV bağımsız]           │
                          │  → EventSink: DB + snapshot + Announcer             │──▶ Ses kartı / HTTP
                          └────────────────────────┬───────────────────────────┘
                             INSERT events         │  UPDATE camera status
                             SELECT config (5 sn)  │
                                                   ▼
                                  ┌──── PostgreSQL 16 (tek DB) ────┐
                                                   ▲
                             CRUD config           │  SELECT events (SSE, 1 sn)
                                                   │
                          ┌────────────────────────┴───────────────────────────┐
                          │ api (FastAPI) + frontend (Vite build, statik)       │◀── HTTP/SSE ──▶ Tarayıcı
                          └─────────────────────────────────────────────────────┘
```

## 2. Repo yapısı

```
dalsan-isg/
├── CLAUDE.md
├── README.md
├── docker-compose.yml           # prod: db + api + analyzer (GPU)
├── docker-compose.dev.yml       # dev: hot reload, CPU, video dosyası kaynağı
├── .env.example                 # tüm değişkenler açıklamalı
├── backend/
│   ├── pyproject.toml
│   ├── alembic/                 # migrasyonlar — 1. günden
│   ├── app/
│   │   ├── core/                # settings, logging, db session, auth
│   │   ├── db/                  # SQLAlchemy modelleri (yalnızca şema)
│   │   ├── schemas/             # Pydantic — validasyon burada
│   │   ├── api/                 # cameras, zones, rules, calibration, events, stream, health
│   │   ├── analyzer/            # source, sampler, detector, ppe_classifier, tracker, pipeline, supervisor
│   │   ├── rules/               # SAF: geometry, calibration, zone, distance, ppe, cooldown
│   │   ├── alerts/              # event_sink, snapshot, announcer (null/audio/http)
│   │   ├── services/            # retention, config_loader, csv_export, ppe_dataset
│   │   ├── main_api.py
│   │   └── main_analyzer.py
│   └── tests/
│       ├── rules/               # birim — CV'siz, hızlı
│       ├── api/                 # entegrasyon
│       └── analyzer/            # video dosyasıyla duman testi
├── frontend/                    # Vite + React + TS + Tailwind
├── deploy/                      # Dockerfile.api, Dockerfile.analyzer, backup.sh, restore.sh, RUNBOOK.md
├── models/                      # ağırlıklar — download.sh, repoya commit YOK
└── docs/                        # bu dosyalar + kkd-politika.md + kalibrasyon rehberi
```

### `rules/` neden saf

`rules/` OpenCV, torch, Ultralytics, SQLAlchemy **import etmez**.
Girdi: `list[Detection]` (sınıf, bbox, track_id, hız, ppe_observation) + bölgeler +
kalibrasyon + kural tanımları. Çıktı: `list[Violation]`.

Sonuç: tüm eşik, cooldown, zamansal oylama ve KKD karar mantığı sentetik veriyle
milisaniyeler içinde test edilir. Yanlış alarm ayarlaması bir tahmin işi değil,
testle doğrulanan bir mühendislik işi olur.

## 3. Veri modeli (MVP — 7 tablo)

| Tablo | Alanlar (özet) | Not |
|---|---|---|
| `cameras` | id, name, **area**, source_type (rtsp/file), source_url, enabled, sample_fps, status, last_frame_at, measured_fps, created_at, updated_at | `source_url` yanıtlarda maskeli. `area` düz metin — fabrika geneli yayılımın ilk adımı. |
| `camera_calibrations` | camera_id (PK/FK), image_points JSONB[4], world_points JSONB[4], homography JSONB[3×3], calibrated_at | 1:1. Yoksa o kamerada mesafe kuralı **pasif**. |
| `zones` | id, camera_id FK, name, zone_type, polygon JSONB, enabled, updated_at | `zone_type`: pedestrian_path · loading_area · truck_parking · vehicle_area · **ppe_required** · restricted. Poligon normalize (0-1) koordinat. |
| `rules` | id, camera_id FK, rule_type, zone_id FK nullable, target_classes JSONB, params JSONB, severity, cooldown_s, announcement_id FK nullable, enabled, updated_at | `rule_type`: zone_intrusion · safe_distance · **ppe_violation**. `params` şeması `rule_type`'a göre Pydantic ile doğrulanır. |
| `events` | id, occurred_at (timestamptz), event_type (violation/system), camera_id FK, rule_id FK (ON DELETE SET NULL), rule_snapshot JSONB, details JSONB, snapshot_path, status (new/reviewed/false_alarm), note, reviewed_at | `rule_snapshot` olay anındaki kural adı/parametrelerini taşır → kural silinse de geçmiş anlamını korur. `details` KKD olaylarında model sürümünü ve gözlem penceresini içerir. İndeks: `(occurred_at)`, `(camera_id, occurred_at)`, `(status)`. |
| `announcement_messages` | id, key, text, audio_file, enabled | 5 mesajla seed: mesafe, yaya yolu, araç konumu, **baret**, **yelek**. |
| `ppe_samples` | id, camera_id FK, captured_at, crop_path, helmet_label, vest_label, source (scheduled/auto/feedback), labeled_at | KKD veri seti. Etiketleme bitince ham crop'lar retention ile silinir. |

### Veri bütünlüğü kararları

- Tüm zamanlar UTC `timestamptz`; UI Europe/Istanbul'a çevirir
- FK'ler açık `ON DELETE` politikalı
- JSONB alanları yazılmadan Pydantic ile doğrulanır (poligon ≥ 3 nokta, normalize aralık; kural `params` şeması tipine göre)
- Snapshot dosyası **önce** yazılır, DB kaydı **sonra** — yetim kayıt olmaz
- Soft delete yok (basitlik)
- Şema değişikliği yalnızca Alembic migrasyonuyla

## 4. Gerçek zamanlı akış (Redis'siz, broker'sız)

Analizör olayı `events` tablosuna yazar. API'nin `/api/v1/stream` SSE endpoint'i
saniyede bir `SELECT ... WHERE id > :last_id` çalıştırıp yeni olayları tarayıcıya iter.
Tek operatör ekranı için bu yük ihmal edilebilir. Gecikme ≤ 1 sn + çıkarım süresi → K4.

Yükseltme yolu (gerekirse): PostgreSQL `LISTEN/NOTIFY` — yine ek altyapı yok.

## 5. Konfigürasyon yayılımı (yeniden başlatmasız)

Analizör 5 sn'de bir `cameras`, `zones`, `rules`, `camera_calibrations` tablolarının
`MAX(updated_at)` değerini sorgular; değişmişse ilgili kamera pipeline'ını yeniden yükler.
Kamera eklenmesi/kaldırılması thread başlatır/durdurur. Restart yok, broker yok.

## 6. Analizör tasarım notları

- **"Son kare" deseni:** RTSP akışı sürekli okunur, işlenmeyen kareler atılır. Aksi halde tampon dolar ve gecikme dakikalara çıkar. Kamera thread'i her zaman en güncel kareyi tutar.
- **Alt akış (substream):** Kameraların düşük çözünürlüklü ikinci akışı kullanılır — **ama KKD bölgelerindeki kameralar için ana akış gerekebilir** (piksel eşiği, bkz. `04-KKD-BARET-YELEK.md` Bölüm 3). Bu, 1. hafta ölçümüyle kamera bazında kararlaştırılır.
- **Kamera izolasyonu:** Bir kameranın hatası yalnızca o thread'i etkiler; supervisor üstel bekleme ile (1→30 sn) yeniden bağlanır. Yeni başlatılan kamera ilk 60 sn `connecting` (bağlanıyor) sayılır ve olay üretmez; 60 sn kare gelmezse `offline` + sebebi yazılı sistem olayı.
- **Kurtarılamaz hata** (GPU) → süreç çıkar, Docker restart eder. Yarım kalan durum yok çünkü tek durum kaynağı DB.
- **Ayak noktası:** Bölge ve mesafe hesabı bbox'ın alt-orta noktasıyla (zemin teması) yapılır; merkez nokta perspektifte yanıltır.
- **KKD çağrısı seyrek:** Kişi track'i başına 5 karede bir, yalnızca KKD bölgesinde, yalnızca piksel eşiği üstünde. Crop'lar kameralar arası toplu (batch) sınıflandırılır.

## 7. Anons adaptörü

```
Announcer (arayüz): play(message_key) -> None
├── NullAnnouncer        # varsayılan; dev + anons altyapısı yoksa prod
├── LocalAudioAnnouncer  # WAV → ses kartı → mevcut amplifikatör (/dev/snd container'a)
└── HttpAnnouncer        # IP hoparlör / anons sunucusu HTTP endpoint'i
```

Seçim: `ANNOUNCER=null|audio|http`. Anons cooldown'u ekran uyarısından **bağımsız ve
daha uzun** (ör. kamera başına 30 sn; KKD için 180 sn). Hoparlör sürekli bağırmamalı.
Hangi somut sınıfın yazılacağı 1. hafta keşfinde belirlenir — yalnızca biri yazılır.
