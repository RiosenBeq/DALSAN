# 02 - Mimari ve Veri Modeli

## 1. Prensip: Modular Monolith, tek program

Tek repo, tek Python paketi (`backend/app/`), tek veritabanı (SQLite: `veri/dalsan.db`)
ve **tek süreç**. İlk tasarım iki süreçti (`api` + `analyzer`, aralarında
PostgreSQL); `09-BASITLESTIRME-KARARLARI.md` #1-#2 bunu tek programa ve SQLite'a
indirdi. Süreç içinde iki taraf vardır:

- **Web** - FastAPI (uvicorn); Jinja2 şablonu + sade JavaScript, derleme adımı yok.
  Konfigürasyon CRUD, olay sorguları, SSE.
- **Analiz** - FastAPI açılırken başlayan arka plan iş parçacıkları
  (`app/uygulama.py` → `AnalizSupervizoru`): görüntü alma, tespit, takip, KKD
  sınıflandırma, kural değerlendirme, olay yazma, anons.

Bu bir microservice ayrımı **değildir**: aynı kod tabanı, aynı ayarlar
(`app/ayarlar.py` → `Ayarlar`). Aralarında mesaj kuyruğu yok; web tarafı
konfigürasyonu ve olayları SQLite'a yazar/okur, canlı durumu (önizleme, kamera
durumu, sayım) bellekteki süpervizörden alır.

```
Kameralar / NVR ──RTSP──▶ ┌────────────── tek program (uvicorn) ───────────────┐
       (3-4 adet)         │ KameraKaynagi (kamera başına okuma iş parçacığı,   │
                          │   "son kare")                                      │
                          │ AnalizSupervizoru (TEK analiz iş parçacığı):       │
                          │  → örnekleme (kamera başına sample_fps, vars. 6)   │
                          │  → Tespitci (YOLOX ONNX, tek oturum, sıralı)       │
                          │  → Takipci (kamera başına ByteTrack)               │
                          │  → KkdSiniflandirici (KKD bölgesindeki kişi)       │
                          │  → KuralMotoru [rules/ - SAF, CV bağımsız]         │
                          │  → olay + kanıt fotoğrafı + AnonsYoneticisi        │──▶ Ses çıkışı / HTTP
                          │ Bekci (analiz takılırsa olay yazar)                │
                          │ FastAPI: sayfalar + /olaylar/akis (SSE, 1 sn)      │◀── HTTP/SSE ──▶ Tarayıcı
                          └─────────────────────────┬──────────────────────────┘
                              olay yaz / oku,       │  konfigürasyon damgası (5 sn)
                                                    ▼
                                  SQLite: veri/dalsan.db (tek dosya)
```

## 2. Repo yapısı

```
dalsan-isg/
├── CLAUDE.md, README.md, BASLARKEN.md, NASIL-CALISIR.md
├── Baslat-Mac.command, Baslat-Windows.bat   # çift tık: Kontrol Paneli
├── .env.example                 # tüm ayarlar açıklamalı
├── pyproject.toml               # pytest + ruff ayarları
├── Dockerfile                   # fabrika: tek container
├── docker-compose.yml           # fabrika: tek servis (docker-compose.ses.yml: host ses çıkışı)
├── LICENSE-THIRD-PARTY          # üçüncü taraf lisans atıfları (YOLOX vb.)
├── backend/
│   ├── requirements.txt
│   ├── sema/                    # 001_ilk.sql ... 011_*.sql - sürümlü şema betikleri (Alembic yok)
│   └── app/
│       ├── main.py              # TEK giriş noktası (uvicorn app.main:app)
│       ├── uygulama.py          # FastAPI fabrikası; analizi başlatır
│       ├── ayarlar.py           # .env okur - tek kaynak
│       ├── veritabani.py        # SQLite bağlantısı, şema uygulama
│       ├── kaynaklar.py, loglama.py, zaman.py, hatalar.py, csv_yazici.py
│       ├── web/                 # rotalar + templates/ (Jinja2) + static/ (sade JS, vendor/)
│       ├── analiz/              # kamera, tespit, takip, kkd_siniflandirici, boru_hatti,
│       │                        #   supervizor, bekci, alan_bulucu, model_indir
│       ├── rules/               # SAF: geometri, kalibrasyon, bolge_ihlali, mesafe, kkd, hiz,
│       │                        #   cooldown, olay_durumu, olay_kodu, sayim, motor
│       ├── olaylar/             # olay yazımı, anons kanalları, dağıtıcı, teslim kaydı, kanal sağlığı
│       ├── nesneler/            # nesne kütüphanesi (Nesneler sayfası)
│       └── egitim/              # KKD veri seti dışa aktarımı + değerlendirme raporu
├── masaustu/                    # Kontrol Paneli (dalsan_launcher.py) + izleme penceresi
├── paketleme/                   # Mac .app / Windows .exe üretimi (PyInstaller)
├── egitim/forklift/             # forklift modelinin eğitimi - ÜRÜN DIŞI
├── models/                      # indir.sh + SHA256SUMS; ağırlıklar repoya commit YOK
├── tests/                       # rules/ (birim, CV'siz, hızlı), test_*.py (entegrasyon), kıyas takımları
├── .github/workflows/           # uygulama-uret.yml, forklift-egit.yml, forklift-egit-bacak.yml
└── docs/                        # bu dosyalar + kkd-politika.md
```

### `rules/` neden saf

`rules/` OpenCV, torch, Ultralytics, sqlite3, FastAPI **import etmez**
(`tests/rules/test_saflik.py` denetler).
Girdi: `list[Tespit]` (sınıf, kutu, takip_id, hız, kkd_gozlemi) + bölgeler +
kalibrasyon + kural tanımları. Çıktı: `list[Ihlal]`.

Sonuç: tüm eşik, cooldown, zamansal oylama ve KKD karar mantığı sentetik veriyle
milisaniyeler içinde test edilir. Yanlış alarm ayarlaması bir tahmin işi değil,
testle doğrulanan bir mühendislik işi olur.

## 3. Veri modeli (SQLite - MVP'nin 7 tablosu + sonraki şemalar)

İlk tasarım PostgreSQL içindi; SQLite'a uyarlanırken (şema 001, 09 #2 ve #6)
JSONB yerine JSON metni (TEXT), `timestamptz` yerine ISO-8601 UTC metni, boolean
yerine INTEGER (0/1) kullanıldı. Parantezli sayı, sütunu sonradan ekleyen şema betiğidir.

| Tablo | Alanlar (özet) | Not |
|---|---|---|
| `cameras` | id, name, **area**, source_type (rtsp/file), source_url, enabled, sample_fps, status, last_frame_at, measured_fps, created_at, updated_at, loop_video (006), privacy_checked_at (010) | `source_url` yanıtlarda maskeli. `area` düz metin - fabrika geneli yayılımın ilk adımı. |
| `camera_calibrations` | camera_id (PK/FK), image_points JSON[4], world_points JSON[4], homography JSON[3×3], calibrated_at | 1:1. Yoksa o kamerada mesafe (ve hız) kuralı **pasif**. |
| `zones` | id, camera_id FK, name, zone_type, polygon JSON, enabled, updated_at | `zone_type`: pedestrian_path · loading_area · truck_parking · vehicle_area · **ppe_required** · restricted · crossing · ppe_exempt (son ikisi şema 007). 007'den beri veritabanında CHECK yok; tipin tek kaynağı `rules/tipler.py` → `BOLGE_TIPI_KODLARI`. Poligon normalize (0-1) koordinat. |
| `rules` | id, camera_id FK, rule_type, zone_id FK nullable, target_classes JSON, params JSON, severity, cooldown_s, announcement_id FK nullable, enabled, updated_at, shadow_mode (002), approved_model_version (008) | `rule_type`: zone_intrusion · safe_distance · ppe_violation · **vehicle_speed** (şema 005). `params` şeması `rule_type`'a göre Pydantic ile doğrulanır. |
| `events` | id, occurred_at, event_type (violation/system), camera_id FK, rule_id FK (ON DELETE SET NULL), rule_snapshot JSON, details JSON, snapshot_path, status (new/reviewed/false_alarm), note, reviewed_at, event_code, severity, resolved_at (007), hold, hold_reason (010) | `rule_snapshot` olay anındaki kural adı/parametrelerini taşır → kural silinse de geçmiş anlamını korur. `details` KKD olaylarında model sürümünü ve gözlem penceresini içerir. İndeks: `(occurred_at)`, `(camera_id, occurred_at)`, `(status)`; 007'den beri ayrıca `(event_code, occurred_at)` ve `(resolved_at)`. |
| `announcement_messages` | id, key, text, audio_file, enabled, updated_at (007) | 5 mesajla seed: mesafe, yaya yolu, araç konumu, **baret**, **yelek**. Şema 007 üç mesaj ekledi: yaya yolunda araç, araç yolunda yaya, yasak alan. |
| `ppe_samples` | id, camera_id FK, captured_at, crop_path, helmet_label, vest_label, source (scheduled/auto/feedback), labeled_at, person_height_px, sharpness, hard_case (008) | KKD veri seti. Etiketlenmemiş kırpıklar `KKD_HAM_VERI_SAKLAMA_GUN` dolunca dosyasıyla silinir; etiketlenenler veri setidir, saklama temizliği onlara dokunmaz. |

Sonraki şemaların eklediği tablolar (bugün toplam 16 tablo + uygulanan betiklerin
kaydı `sema_surumu`):

| Tablo | Şema | Ne tutar |
|---|---|---|
| `speaker_zones` | 002, 009 | Uyarı kanalları: bölüm (`area`), tür (`kind` = ses_karti / http), `device` / `address`, sağlık |
| `library_objects`, `library_object_photos` | 003 | Nesne kütüphanesi (Nesneler sayfası); canlı analizi etkilemez |
| `library_object_diagnosis` | 004 | Nesnenin ne kadar tanınabilir olduğu (teşhis önbelleği) |
| `analysis_hours` | 007 | Kamera × saat analiz süresi ("yanlış alarm / saat" paydası) |
| `ppe_collection_gate` | 007 | KKD veri toplama kapısı (tek satır, başlangıçta kapalı) |
| `alert_deliveries` | 009 | Uyarı teslim kaydı (her deneme ve sonucu) |
| `purge_log`, `access_log` | 010 | İmha kaydı ve erişim izi (KVKK) |

### Veri bütünlüğü kararları

- Tüm zamanlar UTC (ISO-8601 metin, tek kaynak `app/zaman.py`); UI Europe/Istanbul'a çevirir
- FK'ler açık `ON DELETE` politikalı
- JSON alanları yazılmadan doğrulanır: poligon ≥ 3 nokta ve normalize aralık (`web/kameralar.py` → `_poligon_dogrula`); kural `params` şeması tipine göre Pydantic ile (`rules/parametreler.py`)
- Snapshot dosyası **önce** yazılır, DB kaydı **sonra** - yetim kayıt olmaz
- Soft delete yok (basitlik)
- Şema değişikliği yalnızca sürümlü SQL betikleriyle (`backend/sema/NNN_*.sql`, 09 #6): `app/veritabani.py` açılışta uygulanmamış betikleri sırayla, her birini sürüm kaydıyla tek işlemde uygular. Betikler ileri yönlüdür; geri alma betiği yok

## 4. Gerçek zamanlı akış (Redis'siz, broker'sız)

Analiz iş parçacığı olayı `events` tablosuna yazar. `/olaylar/akis` SSE ucu
(`web/olaylar_web.py`) saniyede bir `SELECT ... WHERE id > :son_id` çalıştırıp yeni
olayları - ve "sürüyor" diye gönderdiği olayların bitişini - tarayıcıya iter.
Tek operatör ekranı için bu yük ihmal edilebilir. Gecikme ≤ 1 sn + çıkarım süresi → K4.

Yükseltme yolu (gerekirse): PostgreSQL `LISTEN/NOTIFY` - bugün veritabanı SQLite
olduğu için bu yol ancak PostgreSQL'e geçişle açılır (09 "Ne kaybettik" #1).

## 5. Konfigürasyon yayılımı (yeniden başlatmasız)

Analiz 5 sn'de bir `cameras`, `zones`, `rules`, `speaker_zones`,
`announcement_messages` tablolarının `MAX(updated_at)` değerini, `camera_calibrations`
için `MAX(calibrated_at)`'i ve satır sayılarını tek bir damga olarak sorgular
(`analiz/supervizor.py` → `_konfigurasyonu_yenile`). Damga değişmişse her aktif
kameranın hattına bölge, kural ve kalibrasyon yeniden verilir: takipler ve
değişmeyen kuralın durumu (kalış süresi, KKD penceresi, açık olayı) korunur,
değişen ya da kaldırılan kuralın açık olayı kapanır (`rules/motor.py` →
`kurallari_yukle`). Bağlantısı yeniden kurulan yalnız adresi ya da video döngü
seçimi değişen kameradır. Kamera eklenmesi/kaldırılması okuma iş parçacığı
başlatır/durdurur. Restart yok, broker yok.

## 6. Analizör tasarım notları

- **"Son kare" deseni:** RTSP akışı sürekli okunur, işlenmeyen kareler atılır. Aksi halde tampon dolar ve gecikme dakikalara çıkar. Kamera thread'i her zaman en güncel kareyi tutar.
- **Akış seçimi (ana / alt akış):** Sistem akış seçmez; kamera formuna hangi RTSP adresi yazılırsa o açılır (`analiz/kamera.py`). Hangi akışın yazılacağı `12-KAMERA-VE-GORUNTU-KALITESI.md` §2'de (madde 5: ana akış; alt akış genelde 352x288'dir). KKD bölgelerinde piksel eşiği belirleyicidir (bkz. `04-KKD-BARET-YELEK.md` Bölüm 3); kamera bazında 1. hafta ölçümüyle kararlaştırılır.
- **Kamera izolasyonu:** Bir kameranın okuma hatası yalnızca kendi okuma iş parçacığını etkiler ve o iş parçacığı üstel bekleme ile (1→30 sn) yeniden bağlanır (`analiz/kamera.py`); işleme hatası da süpervizör döngüsünde yalnız o kamerayı atlatır. Yeni başlatılan kamera ilk 60 sn `connecting` (bağlanıyor) sayılır ve olay üretmez; bu sürede hiç kare gelmezse `offline` + sebebi yazılı sistem olayı. Akan görüntü kesilince `offline` kopukluk eşiğinde gelir (`.env KAMERA_KOPUK_ESIGI_SN`, varsayılan 10 sn); "tekrar çevrimiçi" olayı görüntü `KAMERA_UP_KARARLILIK_SN` (5 sn) kesintisiz akınca yazılır. RTSP açılış/okuma zaman aşımı 5/10 sn (`RTSP_*_ZAMAN_ASIMI_MS`).
- **Hata yolları:** Analiz döngüsündeki hata günlüğe yazılır, döngü bir sonraki turda sürer. GPU oturumu açılamazsa model CPU ile açılır ve ana sayfada Türkçe uyarı çıkar (aşağıda). Analiz iş parçacığı takılır ya da ölürse bekçi (`analiz/bekci.py`) `ANALYSIS_STALLED` yazar; `BEKCI_TEPKISI=yeniden_baslat` ise süreç kendini kapatır ki Docker ya da systemd yeniden açsın (masaüstü programında yalnız uyarır). Yarım kalan durum yok çünkü tek durum kaynağı DB.
- **Ayak noktası:** Bölge ve mesafe hesabı bbox'ın alt-orta noktasıyla (zemin teması) yapılır; merkez nokta perspektifte yanıltır.
- **KKD çağrısı seyrek:** Kişi track'i başına 5 karede bir, yalnızca KKD bölgesinde (muaf alan oyulur). Piksel eşiği sınıflandırmadan önce değil, sonra kuralda uygulanır (`rules/kkd.py`). O karedeki kırpıklar tek çağrıda sınıflandırılır; kameralar arası toplu (batch) çağrı yok.

### Önizleme JPEG'i TEMBELDİR (işlemci)

Ölçüldü - kare işleme süresinin dağılımı (bölgeli, tespitsiz):

| Çözünürlük | `isle()` toplam | JPEG kodlama | Payı |
|---|---|---|---|
| 1280x720 | 6,43 ms | 3,86 ms | %60 |
| 1920x1080 | 14,33 ms | 8,95 ms | %62 |

Bu kodlama eskiden **her karede** yapılıyordu - tarayıcıda hiç sayfa açık
olmasa bile. 4 kamera x 6 kare/sn ile bir çekirdeğin **%20'si** karşılığı
olmayan bir işe gidiyordu.

Artık kare saklanır, JPEG **istendiğinde** üretilir ve kare sayacıyla
önbelleklenir. Önizleme sayfası saniyede bir soruyor, hat saniyede altı kare
işliyor: açık sayfada bile 6 kat az iş; sayfa kapalıyken sıfır.

Ölçülen sonuç: `isle()` 1080p'de **14,33 → 6,01 ms** (2,4 kat).

Kodlama kilit DIŞINDA yapılır (1080p'de ~9 ms; o süre analiz iş parçacığını
bekletmenin anlamı yok) ve sonuç yalnızca kare sayacı hâlâ aynıysa
önbelleğe yazılır - aksi halde eski kare yeni karenin yerine servis edilir ve
ekranda donmuş görüntü görünürdü.

### Çıkarım iş parçacığı sayısı

`.env` → `CIKARIM_IS_PARCACIGI`. 0 = otomatik (ONNX Runtime tüm çekirdekleri
kullanır, tek başına çalışan sunucuda en hızlısı). Sunucu başka işler de
yapıyorsa sınırlanır: tespit TÜM kameralar için tek oturumda ve kilitle sıralı
çalıştığı için tek bir çıkarım makinenin tamamını meşgul edebilir.

GPU yolu ayrı bir kod değildir: `CIKARIM_CIHAZI=cuda` seçilince ONNX Runtime
CUDA sağlayıcısını kullanır - sağlayıcı ancak `onnxruntime-gpu` kuruluysa vardır;
`backend/requirements.txt` ve Docker imajı yalnız CPU paketini (`onnxruntime`)
kurar. Sağlayıcı yoksa **sessizce CPU'ya düşmez** -
sistem bunu ana sayfada Türkçe bir uyarı olarak yazar (ADR-002), çünkü
"cuda yazarken CPU'da sürünen sistem" teşhis edilemez bir yavaşlıktır.

## 7. Anons adaptörü

```
Anons kanalı (ayrı arayüz sınıfı yok; iki sınıf aynı yöntemi taşır):
    cal(anahtar, metin, ses_dosyasi, kes=None) -> None
├── SesKartiAnonscu(cihaz)       # WAV → ses çıkışı (kablolu amfi ya da Bluetooth hoparlör)
└── HttpAnonscu(adres, bicim)    # IP hoparlör / anons sunucusu HTTP ucu
```

Seçim: **kanal satırları** (`speaker_zones`, şema 009; docs/17 K22). Her satır
bir kanaldır (`kind` = `ses_karti` | `http`; sınıfı `olaylar/anons.py` →
`kanal_anonscu` seçer); olay, kameranın bölümündeki bütün
açık kanallardan, bölümde kanal yoksa "Tüm fabrika" kanallarından duyurulur
(`olaylar/anons.py` → `bolgeleri_sec`). Hiç kanal yoksa ses çıkmaz, uyarı
yalnızca ekranda görünür. Eski `.env ANONS=null|ses_karti|http` ayarı ilk
açılışta bir kez "Tüm fabrika" kanalına aktarılır (`olaylar/kanallar.py`).
Anons tekrar bastırması ekran uyarısından **bağımsızdır**: anahtarı iz değil
(kamera, mesaj, kanal)'dır, süresi `ANONS_BEKLEME_SN` (varsayılan 30 sn);
kritik olayın açılışı bastırmadan muaftır (`AnonsYoneticisi.duyur`).
Hoparlör sürekli bağırmamalı.

**HTTP biçimi (`ANONS_HTTP_BICIMI`).** Sahadaki IP hoparlörlerin HTTP arayüzü tek
tip değildir; tek bir JSON gövdesi cihazların çoğuyla konuşamaz. Üç biçim
desteklenir:

| Biçim | Gönderilen | Tipik cihaz |
|---|---|---|
| `json` *(varsayılan)* | Gövdede `{"key","text"}` | Anons sunucusu, yazılım geçidi |
| `form` | Gövdede `key=…&text=…` | Gömülü web arayüzlü amfi, röle kartı |
| `get` | Gövde yok; adres çağrılır | "Adresi çağır, sesi çal" hoparlörler |

Adreste `{anahtar}` ve `{metin}` yer tutucuları doldurulur (URL kaçışlı).
`get` biçiminde adresin `{anahtar}` (ya da `{metin}`) yer tutucusu taşıması
**zorunludur** - yoksa her ihlalde aynı ses çalardı; kanal kaydedilirken
reddedilir (`web/hoparlorler.py` → `_adres_dogrula`).

Yer tutucu doldurulurken `str.format` **kullanılmaz**: anons sisteminin kendi
süslü parantezleri (`?q={id}`) `KeyError` fırlatıp anonsu tamamen susturur ve bu,
sahada teşhisi en zor arızadır. Düz metin değişimi yalnız bilinen iki yer
tutucuya dokunur.

Kanal satırındaki "▶ Dene" düğmesi (Komuta → Anons) **aynı** `http_gonder`
yolundan ve **aynı biçimle** gider; ayrılırlarsa deneme "başarılı" derken saha
sessiz kalırdı.

Bağlama tarifi, cihaz soruları ve sorun giderme: `14-ANONS-SISTEMI-BAGLAMA.md`.

## 8. Bölge sayımı (`rules/sayim.py`) - kural DEĞİLDİR

Sayım ayrı bir modüldür ve kural motorundan bağımsız çalışır: **ihlal üretmez,
anons tetiklemez, olay yazmaz.** Ayrı tutulmasının gerekçesi bu ayrımdır -
sayım yanlışsa kimse yanlış uyarı almaz, yalnızca bir sayı yanlış görünür.

Üç sayı, üç ayrı soruyu cevaplar:

| Alan | Soru |
|---|---|
| `anlik` | Şu anda bölgede kaç nesne var? |
| `giren` | Sayaç sıfırlandığından beri kaç **ayrı** nesne girdi? |
| `zirve` | Aynı anda en fazla kaç tane görüldü? |

`giren` **takip bazlıdır**: aynı kişi bölgede on dakika dursa da bir kez sayılır.
Kare bazlı sayım, saniyede altı kare işleyen bir sistemde on dakikada 3600
"kişi" üretirdi.

İki koruma vardır ve ikisi de `bolge_ihlali.py` ile aynı gerekçeye dayanır:
sayılmadan önce **art arda birkaç karede** görülme şartı (sınırdaki titreyen
kutu sayacı zıplatmasın) ve **kayıp toleransı** (tozlu sahnedeki tek karelik
tespit kaçağı "çıktı" sayılmasın).

Bölge çizilen her kamerada kural kurulmadan çalışır: kullanıcı çoğu zaman önce
"kaç kişi geçiyor" sorusunun cevabını ister, uyarıyı sonra kurar.

## 9. Alan tanıma (`analiz/alan_bulucu.py`) - öneri, karar değil

Fabrika zemininde alan **zaten boyalıdır**: yaya yolu sarı çizgilerle, yükleme
alanı beyaz çerçeveyle. Bu modül o boyayı bulup poligon **önerir**; veritabanına
hiçbir şey yazmaz ve hiçbir kuralı etkilemez. Yanlış bir öneri, kullanıcının
kabul etmediği bir çizimdir.

İki geçiş vardır çünkü sahadaki iki işaretleme biçimi farklı davranır:

1. **Kapama geçişi** - kesikli çizgiler ve çerçeveler birleştirilir; dolu bir
   alan (beyaz çerçeveli yükleme sahası) tek konturdan çıkar.
2. **Kümeleme geçişi** - yaya yolu İKİ PARALEL çizgiyle işaretlidir ve aradaki
   boşluk kapama çekirdeğinden kat kat geniştir. Birinci geçiş iki çizgiyi ayrı
   ayrı "çok ince" diye eler; ikinci geçiş birbirine yakın parça kümelerinin
   dışbükey zarfını alır - aradaki yol da alana dahil olur.

Kaynak iki türlüdür: kameranın canlı karesi ya da kullanıcının **yüklediği bir
ekran görüntüsü**. İkincisi, kamera daha takılmadan bölge hazırlamayı mümkün
kılar. **Yüklenen görüntü diske yazılmaz** - bellekte incelenir, tarayıcıya geri
döner. Gerekçe KVKK (fabrika karesinde çalışan vardır; saklamadığımız görüntü
saklama süresi ve silme sorusu doğurmaz) ve en az parçadır (kalıcı olsaydı yeni
tablo, yeni klasör ve bakım döngüsüne yeni istisna gerekirdi).

### Bölgelerin taralı çizilmesi

Bölgeler hem tarayıcıdaki çizim tuvalinde hem **videonun üstünde** çapraz
taramayla doldurulur. Yalnız çerçeve çizmek yetmiyordu: "alanın içi neresi"
sorusu görüntüye bakılarak cevaplanamıyor, yan yana iki bölgede hangi çizginin
hangisine ait olduğu anlaşılmıyordu. İki taraf aynı deseni kullanır, böylece
ekran ile video aynı şeyi söyler.

Tarama bir **vurgu**, örtü değildir: çizgiler çözünürlüğe göre alanın yaklaşık
%7-22'sini kaplar (720p'de ~%7, 1080p'de ~%22; `analiz/boru_hatti.py` →
`_taramayi_hazirla` maskesinden ölçüldü) ve altındaki tespit kutuları okunur kalır
(`test_tarama_alttaki_goruntuyu_ortmez`).

Sunucu tarafında hız kritiktir - 7x24, kamera başına saniyede 6 kare. Üç yol
ölçüldü (1080p, bölgenin sınır kutusu karenin ~%65'i):

| Yöntem | Kare başına |
|---|---|
| Tam kare boolean maskesi + numpy | 22,2 ms |
| Dağınık koordinatlarla fancy-index | 7,2 ms |
| **Sınır kutusunda `cv2.addWeighted` + `copyTo`** | **1,1 ms** |

Fark aritmetikte değil **bellek erişimindedir**: 164 bin dağınık koordinata tek
tek gitmek, bitişik bir bloğu baştan sona taramaktan pahalıdır. Maske, renk katı
ve harman tamponu bölge çizimi değişmedikçe yeniden üretilmez.

Tarama aralığı ve çizgi kalınlığı karenin kısa kenarına **oranlıdır**: sabit
piksel, 480p'de seyrek görünürken 1080p'de saç teli gibi sıklaşıyordu - hem
çirkin hem gereksiz pahalıydı.

### Çizim arka planı

Kullanıcı çizim yaparken arka planı seçebilir: canlı akış (varsayılan), **dondurulmuş
kare** ya da **yüklenen ekran görüntüsü**. Dondurma, önizleme betiğinin okuduğu
`data-donmus` özniteliğiyle yapılır - tazeleme durur, kare ekranda kalır. Canlı
akış saniyede yenilendiği için köşe tıklamak aksi halde zordur.

Alan bulunamadığında bir **teşhis görüntüsü** döner: sistemin "boya" saydığı
pikseller işaretlidir. Kullanıcı "neden bulamadı" sorusunun cevabını ekranda
görür; boş bir maske, eşik oynamaktan daha açık bir yanıttır.
