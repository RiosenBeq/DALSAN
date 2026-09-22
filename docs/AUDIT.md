# DALSAN — Faz 0 Keşif ve Denetim Raporu

> Ölçülen yarı: docs/AUDIT-OLCUM.md · Gereksinimler: docs/GOREV-TANIMI-V2.md

Tarih: 22 Eyl 2026 (aynı gün bir düzeltme turundan geçti, bkz. §12). Kapsam: `/home/user/dalsan`
(RiosenBeq/DALSAN, `main`). Yöntem: salt okuma (`cat/sed/grep/find/ls/wc`; donanım için
yalnız okuyan `lscpu`, `free -h`, `df -h`, `docker --version`). Bu raporun yazımı sırasında
hiçbir dosya değiştirilmedi (bu dosya hariç); git, uvicorn ve Python çalıştırılmadı. Test
sonuçları ve ölçümler başka koşulardan aktarılmıştır, kaynakları her satırda yazılıdır.
`tasks/*.output` dosyaları depoda değildir, oturumun geçici klasöründe durur
(`/tmp/claude-0/-home-user-lafmobil/9519d0a6-b2f2-5ba6-8a76-c8a91b7363f5/tasks/`); okuyucu
bunları doğrulayamaz. Satır numaraları bu raporun yazıldığı andaki çalışma kopyasına
göredir. Durum etiketleri: `exists` (var), `partial` (kısmi), `missing` (yok), `conflict`
(belgelenmiş bir karar gereksinimi reddediyor ya da erteliyor).

## 0. Özet

- **Sistem:** tek süreçli FastAPI + tek "analiz" iş parçacığı (`supervizor.py:58`); 3-4 RTSP/dosya kamera → YOLOX ONNX (CPU) → ByteTrack → saf kural motoru (4 tip) → SQLite olay + kanıt JPEG → anons (null/ses kartı/HTTP) + SSE ekran bandı.
- **Ne kadarı var:** §4'ün 125 maddesinden 21 exists, 54 partial, 29 missing, 21 conflict (§8). Tam paket 1023 geçti, 17 atlandı, 0 başarısız (§5). Sistem ayağa kalkıyor; denenen 15 adresin 14'ü 200 döndü, 404 dönen biri var olmayan bir adresti (AUDIT-OLCUM §2.2, ham çıktısıyla).
- **Ölçüm:** CPU'da 4 kamera × 6 fps bütçesi `yolox_tiny` ile %100, fabrika modeli `yolox_s` ile %40 (AUDIT-OLCUM §1.2); GPU yolu teslim edilemiyor (AUDIT-OLCUM §1.3-4).
- **En büyük 5 risk:** (1) KKD sınıflandırıcı yok → PPE olayı hiç üretilmez (`kkd_siniflandirici.py:54-59`); (2) forklift sınıfı yok, car/bus/truck tek "truck" (`tespit.py:31-36`); (3) `onnxruntime-gpu` hiçbir yerde kurulmuyor (`requirements.txt:21`) → fabrika yapılandırması CPU'da bütçeyi karşılamaz; (4) RTSP okuma zaman aşımı yok (`kamera.py:279`) + bekçi yok + tüm kalıcılık tek analiz iş parçacığında; (5) kimlik zayıf: XFF ile atlanan kaba kuvvet kilidi (`giris.py:94`), CSRF/Origin kontrolü yok, yönetici şifresi Ayarlar sayfasında düz metin (`komuta_ayarlar.html:48`).
- **En büyük 5 boşluk:** (1) olay durum makinesi, `resolved_at`, histerezis, önem seviyeleri; (2) çok kanallı `AlertDispatcher` (öncelik kuyruğu, eşzamanlı kanallar, periyodik kanal sağlığı, `AUDIO_CHANNEL_DOWN`); (3) doğruluk ölçüm takımı (recall/mAP) ve eğitim hattı (`egitim/` yok); (4) Prometheus metrikleri, readiness, işlenen-fps/gecikme ölçümü; (5) `docs/KVKK.md`, yüz bulanıklaştırma, rol/denetim günlüğü.

## 1. Depo haritası

| Yol | İçerik |
|---|---|
| `backend/app/main.py` | Tek giriş MODÜLÜ (63 satır): `uygulamayi_kur()` (`main.py:32-60`) ve modül düzeyi `app = uygulamayi_kur()` (`:63`). İki çağıranı `:35-43`'te yazılı; ayrıntı aşağıdaki "Giriş noktaları" |
| `backend/app/uygulama.py` | FastAPI fabrikası `uygulama_olustur(ayarlar, analiz=True)` (`:41`). Lifespan `yasam_dongusu` (`:47-48`), `FastAPI(lifespan=…)` ile bağlanır (`:93`): önce şema (`:60-63`), sonra `analiz` True ise `AnalizSupervizoru` kurulup başlatılır (`:79-85`). 15 `include_router` (`:105-135`) |
| `backend/app/ayarlar.py` | `.env` tek kaynak (python-dotenv), 33 anahtar |
| `backend/app/veritabani.py` | SQLite (FK, WAL, `busy_timeout=5000` `:68`), sürümlü şema |
| `backend/app/` kök yardımcılar | `loglama.py` (106 satır, JSON günlük), `zaman.py` (157, tek saat kaynağı: UTC saklanır, İstanbul gösterilir), `hatalar.py` (158, tiplenmiş hatalar + FastAPI yakalayıcısı), `kaynaklar.py` (156, paketlenmiş programda kaynak ve yazılabilir veri yolları), `__init__.py` |
| `backend/app/analiz/` (11 dosya) | kamera (323), tespit (275), takip (86), boru_hatti (499), supervizor (810), kkd_siniflandirici (59), goruntu (96), alan_bulucu (380; zemin boyasından HSV ile bölge önerisi), model_indir (158), model_adi (37; dosya adı → "NextGen AI Hızlı/İsabetli", `model_adi.py:17-25`), `__init__` (5) |
| `backend/app/rules/` (12 dosya, `__init__` dahil) | saf karar mantığı: motor, bolge_ihlali, mesafe, kkd, hiz, sayim, cooldown, kalibrasyon, parametreler, tipler, geometri (25 satır; ışın yöntemiyle nokta-poligon testi, `geometri.py:6-10`) |
| `backend/app/olaylar/` (5 dosya) | yazici (olay + kanıt), anons, ses_cihazlari, test_sesi, `__init__` |
| `backend/app/web/` (17 `.py`, `__init__` dahil) | rotalar, komuta (1238), kameralar, alan_rotalari (234; `POST /kameralar/{id}/alan-bul` `:50`), kurallar, olaylar_web (SSE), rapor, videolar, kkd_web, anons_web, hoparlorler, nesne_rotalari (314; 8 `/nesneler*` rotası `:37-227`), giris, ayar_rotalari, kilavuz (384; ekran açıklamaları + kurulum listesi), ortak (426; istek başına DB bağlantısı, RTSP maskeleme, etiket tabloları, hazır kurallar). `templates/` 28 dosya, `static/` 15 dosya (4'ü `vendor/`). Toplam 72 rota (§4.6) |
| `backend/app/nesneler/` (5 dosya) | Nesne kütüphanesi; canlı analize girmez (`nesneler/__init__.py:1-8`). kutuphane (699; ORB+HSV parmak izi, `kabul_skoru`), arama (328; yüklenen fotoğrafta kayan pencere tarama, `arama.py:1-22`), depo (240; `library_*` tabloları + `veri/nesneler/` dosyaları, bakım döngüsüne girmez `depo.py:1-10`), teshis (566; ölçümü kullanıcının diline çevirir, `teshis.py:1-12`) |
| `backend/sema/` | 001–006 SQL betikleri |
| `masaustu/` | Kontrol Paneli (tkinter), izleme penceresi |
| `paketleme/` | PyInstaller tarifleri (.app/.exe), açılış kancası |
| `models/` | `indir.sh`; `yolox_tiny.onnx`, `yolox_s.onnx` (git'te değil) |
| `tests/` | 50 `test_*.py` + `rules/` (8 dosya) + `nesne_kiyas/` + `hiz_kiyas/` |
| `Dockerfile`, `docker-compose.yml` | fabrika için tek container |

**Giriş noktaları** (backend/app altında 59 `.py`; tek giriş modülü `main.py`):

- **uvicorn CLI yolu**, modül düzeyi `app` sembolünü (`main.py:63`) kullanır: Docker
  `CMD python -m uvicorn app.main:app --host 0.0.0.0 --port 8080` (`Dockerfile:40`) ve Kontrol
  Paneli'nin geliştirmedeki alt süreci (`dalsan_launcher.py:948-949`,
  `uvicorn app.main:app --host <SUNUCU_ADRESI> --port 8080`); `main.py:3` docstring'i de bunu yazar.
- **Paketlenmiş program** hazır `app` nesnesini bilerek kullanmaz: `from app.main import
  uygulamayi_kur` ile her "Sistemi Başlat"ta fabrikayı yeniden çağırır ve dönen nesneyi kendi
  sürecindeki `uvicorn.Server`'a verir (`dalsan_launcher.py:603-620`). Yan etki: ilk başlatmada
  `app.main`'in içe aktarılması `main.py:63`'ü de çalıştırır, yani `uygulamayi_kur()` iki kez
  çağrılır ve ilk kurulan `app` sunulmaz. Lifespan yalnız sunulan nesnede koştuğu için ikinci
  bir süpervizör başlamaz (kod okuması).
- Her iki yolda da analiz süpervizörü `uygulama.py` lifespan'i içinde, `analiz=True` iken
  başlar (`uygulama.py:41`, `:79-85`); `main.py:60` `analiz`'i değiştirmez.
- Sağlık: `GET /saglik` (`rotalar.py:129`), kimliksiz `acik_router` (`uygulama.py:106`).

**Çalışma zamanı:** hedef Python 3.12 (`CLAUDE.md:42`, `Dockerfile:3`, `pyproject.toml:8`);
bu konteynerdeki `.venv` **3.11.15** (`.venv/pyvenv.cfg`); Kontrol Paneli alt sınırı 3.11, üst
sınır yok (`dalsan_launcher.py:209`). CUDA: yok (sağlayıcılar Azure+CPU, AUDIT-OLCUM §1).

**Paket listesi** (`.venv/lib/python3.11/site-packages/*.dist-info`; `tasks/bkf4oi06k.output`'taki
`Python 3.11.15` + `pip list` çıktısıyla aynı):

| Grup | Sürümler |
|---|---|
| Sabit (`requirements.txt:20-23`) | opencv-python 4.10.0.84 · onnxruntime 1.19.2 (CPU) · supervision 0.25.1 |
| Sabitsiz web | fastapi 0.141.1 · starlette 1.6.0 · pydantic 2.13.5 · uvicorn 0.53.0 · jinja2 3.1.6 · python-dotenv 1.2.3 · python-multipart 0.0.32 |
| Sabitsiz diğer | numpy 2.4.6 · httpx 0.28.1 · pytest 9.1.1 · ruff 0.16.8 |
| Geçişli | scipy 1.17.1 · matplotlib 3.11.2 · pillow 12.3.0 · pyyaml 6.0.3 · requests 2.34.2 · protobuf 7.36.2 · uvloop 0.22.1 · websockets 17.1 |
| Kurulu değil | onnxruntime-gpu · tzdata (yalnız win32) · pyinstaller (ayrı dosya) |

## 2. Mevcut video hattı

| # | Adım | Dosya:fonksiyon:satır | Not |
|---|---|---|---|
| 1 | Kaynak | `analiz/kamera.py:KameraKaynagi._ac:211`, `cv2.VideoCapture(url, CAP_FFMPEG)` `:223`; `_on_kontrol:230` (TCP 3 sn `:252`). Video yükleme: `POST /videolar/yukle` (`web/videolar.py:201`) → `source_type='file'` kamera; `loop_video` (`sema/006:31`, varsayılan 1): 0 ise tek geçiş, sonda `finished` (`kamera.py:59`, `:80`, `:282-287`); değişince kaynak yeniden kurulur (`supervizor.py:365-385`) | Yalnız `rtsp`/`file` (`sema/001_ilk.sql:20`); USB yok; RTSP-over-TCP `:38` |
| 2 | Çözme | `_okuma_dongusu:274`, `read():279`, son kare üzerine yazılır `:309` | Kuyruk yok; okuma zaman aşımı yok |
| 3 | Yeniden bağlanma | `_dongu:140`, `_bir_tur:169`; 1→30 sn `:47-48`; `durum:119`, 60 sn `:50` | Kamera iş parçacığında, süpervizörde değil |
| 4 | Örnekleme | `supervizor.py:_kameralari_isle:511`; fps `:516`; aynı kare atlanır `:522-524` | Tek "analiz" iş parçacığı `:58`; tur 50 ms `:255` |
| 5 | Ön işleme | `boru_hatti.py:KameraHatti.isle:162`; kalite 50 karede 1 `:171`; CLAHE `:174-177`; `tespit.py:_on_isle:181` letterbox dolgu 114 `:183` | Normalizasyon yok; BGR/RGB beklentisi DOĞRULANMADI |
| 6 | Model | `tespit.py:tespit_et:169`, kilit `:175` (nesne `:159`), `InferenceSession` `:103`, sağlayıcı `:86-90` | Tek oturum, tüm kameralar sıralı |
| 7 | Son işleme | `tespit.py:_son_isle:191`; ilgi sınıfları `:217`; NMS `:261` (skor × 0.9 `:266`); ad `:274` | Sınıf eşlemesi `:31-36` |
| 8 | Takip | `takip.py:Takipci.guncelle:46`; `sv.ByteTrack(frame_rate=…)` `:32` | Yalnız frame_rate verilir |
| 9 | KKD | `boru_hatti.py:_kkd_degerlendir:286`; `model_var` False → döner `:293`; bölge `:276-280` | Yer tutucu |
| 10 | Kural | `boru_hatti.py:189` → `rules/motor.py:KuralMotoru.degerlendir:106`; hız `:134-155` | 4 değerlendirici `motor.py:25` |
| 11 | Sayım | `boru_hatti.py:200` → `rules/sayim.py` | Kural değil, olay üretmez |
| 12 | Overlay | `boru_hatti.py:_overlay_guncelle:312` (`kare.copy()` `:315`); tembel JPEG `son_islenmis_jpeg:238` | Overlay her karede çizilir |
| 13 | Çıktı | `supervizor.py:_ihlali_kaydet:544` → `olaylar/yazici.py:ihlal_yaz:22` → gölge mod `:555` → `_anons.duyur` `:563`; KKD örneği `:582/:600`; durum `:642`; önizleme `:185`; SSE `web/olaylar_web.py:98` | Kalıcılık analiz iş parçacığında |

Ölçüm (AUDIT-OLCUM §1.2): bu hat CPU'da `yolox_tiny` ile 4 kamera × 6 fps bütçesinin %100'ünü,
`yolox_s` ile %40'ını karşılıyor; kilit sıralaması gecikmeyi p90 121–138 ms'ye çıkarıyor.

## 3. Mevcut model(ler)

| Model | Arayüzdeki ad | Mimari / dosya | Eğitim verisi | Lisans | Ölçülmüş metrik |
|---|---|---|---|---|---|
| Tespit | `yolox_tiny.onnx` → "NextGen AI Hızlı", `yolox_s.onnx` → "NextGen AI İsabetli", başka dosya → "NextGen AI (özel model)" (`model_adi.py:17-28`); README'deki "NextGen AI tespit motoru" (`README.md:41`) budur, `LICENSE-THIRD-PARTY` §1 YOLOX'a bağlar | YOLOX tiny (416) / s (640); girdi boyu modelden `tespit.py:140`. Ham çıktı 85 sütun (4 kutu + 1 nesnellik + 80 COCO). tiny için satır sayısı 3549 = 52² + 26² + 13² (416 px, adımlar 8/16/32, `tespit.py:195-202`); `(1,3549,85)` şekli bir çıkarımda gözlendi ama o koşunun kaydı yok, sayı buradaki aritmetikle tutarlı. `yolox_tiny.onnx` 20 219 662 B (20,2 MB), `yolox_s.onnx` 35 858 002 B (35,9 MB) (`ls -l models/`, `tasks/by392r477.output:1-2`, `tasks/bfdl1ou83.output`) | Hazır COCO ağırlığı, YOLOX 0.1.1rc0 yayını (`model_indir.py:21`); saha ince ayarı yok | Apache-2.0 (`LICENSE-THIRD-PARTY`); `docs/05:65-66` ADR-002 hâlâ "AÇIK" | Doğruluk **ölçülmedi**; hız AUDIT-OLCUM §1 |
| KKD | — | Yer tutucu: `kkd_siniflandirici.py:47-59`; `supervizor.py:90` `KkdSiniflandirici(None)` | Yok; yalnız kırpık toplama `supervizor.py:582-638` | — | Yok |
| Nesne kütüphanesi | "Nesneler" sayfası (`/nesneler`) | Model değil: ORB+HSV parmak izi (`nesneler/kutuphane.py`), canlıya girmez | Sentetik tohumlu takım `tests/nesne_kiyas` (12 nesne × 4 referans fotoğraf, toplam 264 sorgu; bunun 204'ü nesneyi içeren pozitif sorgudur, `teshis.py:15-17`, `:118`, `:295`; kalan 60'ın negatif olduğu farktan çıkarılır, DOĞRULANMADI) | — | Kalite kapısı yeşil (tam paket). "8/204 isabet, 0 yanlış isim, çıta 0,24" kod yorumunda (`kutuphane.py:177-180`, `teshis.py:413-417`) ve `docs/07:167`'de ("61/204 → 8/204"); bu raporda yeniden koşulmadı |

Sınıf eşlemesi (`tespit.py:31-36`) ve kapalı liste (`rules/tipler.py:35`):

| COCO id | COCO | Sistem sınıfı | Not |
|---|---|---|---|
| 0 | person | person | ayrı eşik `TESPIT_INSAN_GUVEN_ESIGI=0.28` (`ayarlar.py:294`) |
| 2 | car | truck | "GEÇİCİ" (`tespit.py:28`) |
| 5 | bus | truck | |
| 7 | truck | truck | genel eşik 0.35 (`ayarlar.py:293`) |
| — | — | forklift | `TANINAN_SINIFLAR`'da var, model hiç üretmez |

Bütünlük: model indirmede tek içerik denetimi dosyanın en az 1 MiB olmasıdır
(`model_indir.py:79-85`; tam 1 MiB olan dosya da geçer). `Content-Length` okunur ama indirilen
bayt sayısıyla karşılaştırılmaz, yalnız ilerleme çubuğuna gider (`:69`, `:77-78`).
`BILINEN_MODELLER` yalnız ad listesidir, özet değeri yoktur (`:22`). `model_indir.py`'de
`hashlib` yoktur; SHA-256 doğrulaması yapılmaz (`backend/app`'te `hashlib` yalnız `web/giris.py:31,63,67`'de
geçer, oturum imzası için). `.part` → yeniden adlandırma (`:65`, `:86`) yarım dosyanın model
sayılmasını önler, ama bu bir içerik doğrulaması değildir. `models/indir.sh:10-15`'te boyut
denetimi de yoktur, yalnız `curl --fail` vardır. Bozuk dosya yükleme anında
`InferenceSession` hatasıyla `ModelHatasi`'na çevrilir (`tespit.py:103-117`); bu bir indirme
denetimi değildir. (`model_indir.py:21` yalnız yayın adresidir.) Model sürümü olaylara
yazılmıyor (yalnız KKD `details.ppe.model_version`, `rules/kkd.py`).

## 4. Mevcut uyarı mekanizması, kayıt, arayüz, yapılandırma

### 4.1 Anons adaptörleri

| Parça | Yer | Davranış |
|---|---|---|
| `NullAnonscu` | `anons.py:46` | Ses yok, `AnonsHatasi` |
| `SesKartiAnonscu` | `anons.py:103`; komut `:60-100` | Linux paplay→aplay (`:89`), macOS afplay, Windows PowerShell SoundPlayer; zaman aşımı 20 sn `:143` |
| `HttpAnonscu` | `anons.py:224`; `http_gonder:197` | json/form/get, `{anahtar}`/`{metin}`; 5 sn `:210`; yük yalnız `{key,text}` |
| Seçim | `anonscu_kur:267`; `ayarlar.py:28,233` | `.env ANONS` ile TEK adaptör; değişince restart |
| Yönetici | `AnonsYoneticisi:275`; `duyur:307` | Cooldown anahtarı (kamera, mesaj) `:313-314`, `ANONS_BEKLEME_SN=30` (`ayarlar.py:314`); her anons yeni daemon thread `:331` |
| Hoparlör bölgeleri | `bolge_sec:245`; `sema/002`; `web/hoparlorler.py` | Yalnız HTTP yolunda anlamlı |
| Gölge mod | `supervizor.py:555-557`; `sema/002:55` | Olay yazılır, anons çalmaz |

Kanal soyutlaması, hoparlör bölgeleri ve test sesi ZATEN var (AUDIT-OLCUM §2.3); öncelik
kuyruğu, eşzamanlı kanallar ve `health()` yok.

### 4.2 Bluetooth'un bugünkü durumu

- Eşleştirme işletim sisteminde: "Program eşleştirmeyi kendisi yapmaz" (`docs/14:55`).
- Listeleme `ses_cihazlari.py:cihazlari_listele:77`; liste alınamazsa boş döner, hata fırlatmaz (`:84-95`).

  | Platform | Listeleme | Bluetooth tanıma | Seçim | Not |
  |---|---|---|---|---|
  | Linux | `pactl list short sinks` + `get-default-sink` (`:142-159`) | sink adı `bluez_output…` güvenilir bir işarettir (`:51-53`, `:177`) | Var: `paplay --device=` / `aplay -D` (`anons.py:92-99`) | `pactl` yoksa `aplay -L` yedeği (`:160-169`). ALSA, Bluetooth çıkışını görmez (`anons.py:84-88`), yani bu yedekte BT hiç listelenmez |
  | macOS | `system_profiler -json SPAudioDataType` (`:187`), yalnız çıkış cihazları (`:195`) | `coreaudio_device_transport` alanı + ad (`:200`, `:206`); alanın gerçek değerleri DOĞRULANMADI | Yok (`:68-74`); çıkış OS'tan seçilir | varsayılan işaretlenir (`:205`) |
  | Windows | `Get-PnpDevice -Class AudioEndpoint` (`:217-220`) | yalnız ad izleri (`bluetooth`, `airpods`, `jbl`, `soundlink`, `bose`; `:53`, `_bluetooth_mu:113`) | Yok | varsayılan işaretlenmez (`:226-228`) |

- `cihaz_bagli_mi:98` üç durumludur (True/False/None) ama yalnız `/anons` render edilirken çağrılır (`anons_web.py:81`, `ses_cikisi_baglami` tek çağıranı `anons_web.py:62`); periyodik yoklama ve `AUDIO_CHANNEL_DOWN` yok.
- **Kör nokta:** seçim boşsa `cihaz_bagli_mi('')` her durumda True döner (`ses_cihazlari.py:105-106`). Mac ve Windows'ta seçim formu hiç gösterilmediği için (`secim_destekleniyor_mu` False, `:68-74`; `anons.html:59`) seçim hep boştur. Sonuç: bu iki platformda, ve Linux'ta seçim yapılmamışsa, Bluetooth kopması **hiçbir zaman** algılanmaz; sayfa gri "işletim sisteminin varsayılanı" rozeti gösterir (`anons.html:49`).
- **Bilinmiyor = "bağlı" rozeti:** liste okunamazsa (`None`) ve bir seçim varsa rozet yeşil "bağlı" yazar, çünkü şablon yalnız `is false`'u ayırır (`anons.html:47-49`). Altta "Ses çıkışları listelenemedi" notu çıkar (`anons.html:119-121`), ama başlıktaki rozet yanlıştır. Kod okumasına dayanır, render edilerek DOĞRULANMADI.
- Seçim yalnız Linux'ta uygulanır (`ses_cihazlari.py:68-74`). Seçim `.env ANONS_SES_CIHAZI`'ya doğrulamasız yazılır (`anons_web.py:100`) ve bu **bilinçli** bir karardır: Bluetooth hoparlör kapalıyken listede görünmez, doğrulama yapılsaydı kayıtlı ad silinirdi (`anons_web.py:95-97`; şablon da kapalı cihazı seçenek olarak ekler, `anons.html:73-77`). Yan etki: R14 (`.env` satır enjeksiyonu) bu uçtan da tetiklenebilir.
- **Seçimden sonra bayat durum:** `app.state.ayarlar` yalnız açılışta kurulur (`uygulama.py:94`); `POST /anons/ses-cikisi` yalnız `.env`'i yazar (`anons_web.py:100`), bellekteki ayarı güncellemez. Bu yüzden yeniden başlatılana kadar sayfa eski seçimi gösterir (`anons_web.py:75`) ve "Test sesi çal" ESKİ çıkışa çalar (`anons_web.py:119`). Kayıt mesajı yeniden başlatma gerektiğini söyler (`anons.html:28-29`; test `test_ses_cikisi.py:264-272`), ama test sesi sonrası "başka bir çıkış seçip tekrar deneyin" yönlendirmesi (`anons.html:31-32`) bu yüzden yanıltıcıdır. Kod okumasına dayanır, çalıştırılarak DOĞRULANMADI.
- Kanal sağlığı yalnız ses kartı yolunda görünür: "Ses çıkışı" kartı `anons_yolu == 'ses_karti'` koşuluna bağlıdır (`anons.html:41-44`). HTTP anons yolunda (IP hoparlör) kanal sağlığını gösteren hiçbir şey yok; yalnız "Son deneme" satırı var (`anons.html:18-20`).
- `/komuta/anons` ekranı (`komuta.py:235-240`, `komuta_anons.html`) ses çıkışını ve Bluetooth bağlılığını hiç göstermez; yalnız `/anons` sayfasına bağlantı verir (`komuta_anons.html:34`). Oysa `ses_cikisi_baglami` docstring'i "komuta kabuğundaki anons ekranı aynı tabloyu göstermeli" der (`anons_web.py:69-72`); `grep -rn ses_cikisi_baglami backend/app` yalnız `anons_web.py:62` ve `:67`'yi döndürür (§10).
- Test sesi: `POST /anons/test-sesi` (`anons_web.py:104-122`, `test_sesi.py:44-98`); `ANONS≠ses_karti` iken 400 (`anons_web.py:114-118`).
- Tarayıcı kanalı: `uyari.js:70-78` `speechSynthesis` `tr-TR` seslendirme, `:50-68` bip, bant 8 sn (`uyari.js:94`, `setTimeout … 8000`). Seslendirme ve bip hataları boş `catch` ile sessizce yutulur (`uyari.js:77`, `:67`), yani ekranda ya da günlükte iz kalmaz. uyari.js'i yalnız `ana_sayfa.html:123-124`, `olaylar.html:88-89` ve `anons.html:166` yükler; komuta ekranları yüklemez.
- **Fabrika container'ında ses/Bluetooth yolu yok:** `Dockerfile:10-12` ses aracı kurmaz (`alsa-utils`/`pulseaudio-utils` yok, yani `aplay`/`paplay`/`pactl` yok). Bu durumda `SesKartiAnonscu` açılışta "komut bulunamadı" der ve her anonsta `AnonsHatasi` verir (`anons.py:117-127`); listeleme boş döner (`ses_cihazlari.py:142`, `:160-161`). `docker-compose.yml:47-50` yalnız `/dev/snd` (ALSA) bağlamayı önerir; PulseAudio/PipeWire soketi ya da BlueZ D-Bus bağlanmaz, ALSA da Bluetooth'u görmez (`anons.py:84-88`). Hata metnindeki `apt install alsa-utils` önerisi (`anons.py:121`) ve docs/14'teki aynı çözüm container'da değil, host'ta işe yarar. İmaj derlenmedi; `ffmpeg` paketinin bağımlılıklarının `aplay` getirmediği varsayıldı (DOĞRULANMADI).
- Bu konteynerde `bluetoothctl`, `aplay`, `pactl`, `paplay` yok (`command -v`, §6) → ses/Bluetooth yolu burada sınanamaz.
- Testler: `tests/test_ses_cikisi.py` (22 test) sahte `subprocess`/`_calistir` ile komut seçimini (`:28-95`), `pactl` çözümlemesini ve BT işaretini (`:132-150`), üç durumu (`:153-172`), kopma kırmızı yazısını (`:238`), `.env`'e yazmayı (`:264-272`) ve test sesini (`:175-215`, `:275-279`) sınar. Gerçek ses donanımıyla test yok.

### 4.3 Olay kaydı ve SSE

- `yazici.py:ihlal_yaz:22`: fotoğraf önce (`_fotograf_kaydet:92`, `veri/goruntuler/YYYY-AA/…jpg` `:107`), INSERT sonra; `sistem_olayi_yaz:64`.
- Retention `supervizor.py:_bakim_yap:714-753` (açılışta + 24 sa; ayrı "bakim" iş parçacığı `:712`); disk uyarısı `:742-753`.
- SSE `olaylar_web.py:98-142`: `async` gövdede senkron SQLite, 1 sn yoklama `:134`, `LIMIT 20` `:112`; `sse-starlette` kurulu değil.

### 4.4 Yapılandırma (.env) ve günlük

- `.env.example` 33 anahtar; `tests/test_ayarlar.py` kod↔örnek iki yönlü eşitler.
- Ayarlar sayfası (`web/ayar_rotalari.py`) `.env`'i yazar; etki yeniden başlatınca (`komuta_ayarlar.html:21`).
- DB tarafı restart'sız: 5 sn'lik damga (`supervizor.py:329-341`) cameras/zones/rules/camera_calibrations/speaker_zones; **`announcement_messages` damgada yok**.
- Günlük JSON satır: `{"ts","level","bilesen","mesaj"}` (`loglama.py:45-52`); dosyada ek `ayrinti` alanı (`:53-61`, `:100`), ekranda yok (`:92`). Dosya 5 MB × 3 (`:97-99`), seviye sabit INFO (`:85`). AUDIT-OLCUM §2.1'de çalışır halde gözlendi. JSON biçimleyici yalnız uygulamanın kök logger'ına bağlıdır ve `propagate=False`'tur (`:84-101`). Bu yüzden uvicorn CLI yolunda (Docker, geliştirme) uvicorn'un kendi erişim/hata satırları uvicorn'un varsayılan düz metin biçimiyle çıkar ve `sistem.log`'a girmez (kod okuması, DOĞRULANMADI).
- Sağlık: `GET /saglik` her koşulda `{"durum":"calisiyor","analiz":<süpervizör nesnesi var mı>,"model":<model_durumu>}` döner (`rotalar.py:136-141`); AUDIT-OLCUM §2.2 gövdesi (`"analiz":true,"model":"hazir"`) bununla tutarlı.

### 4.5 Veritabanı şeması (006 sonrası; 11 tablo + `sema_surumu`)

| Tablo | Betik | Önemli sütun/kısıt | İndeks | Yabancı anahtar (ON DELETE) |
|---|---|---|---|---|
| `sema_surumu` | `veritabani.py:92` | uygulanan betikler | — | — |
| `cameras` | 001:16; 006:31 | `source_type` CHECK rtsp\|file; `sample_fps` DEFAULT 6; `loop_video` | `idx_cameras_area` (001:32) | — |
| `camera_calibrations` | 001:35 | 4 nokta + 3×3 homografi JSON | — | `camera_id` → cameras CASCADE (001:37) |
| `zones` | 001:45 | `zone_type` CHECK 6 tip (`:50-52`); normalize poligon JSON | — | `camera_id` → cameras CASCADE (001:48) |
| `announcement_messages` | 001:59 | 5 tohum mesaj; `updated_at` YOK | — | — |
| `rules` | 001:76; 005:44 (yeniden kurma); 002:55 | `rule_type` CHECK 4 tip; `params`/`target_classes` JSON; `cooldown_s`; `severity`; `shadow_mode` | — | `camera_id` → cameras CASCADE (001:79, 005:47); `zone_id` → zones CASCADE (001:84, 005:52); `announcement_id` → announcement_messages SET NULL (001:89, 005:57) |
| `events` | 001:95 | `event_type` CHECK violation\|system; `status` CHECK new\|reviewed\|false_alarm; `rule_snapshot`, `details`, `snapshot_path` | `idx_events_occurred_at`, `idx_events_camera_occurred` (camera_id, occurred_at), `idx_events_status` (001:112-114) | `camera_id`, `rule_id` SET NULL (001:100-101); olay, kamera/kural silinse de kalır |
| `ppe_samples` | 001:117 | etiket CHECK yes\|no\|unknown; `source` CHECK scheduled\|auto\|feedback | — | `camera_id` SET NULL (001:120) |
| `speaker_zones` | 002:30 | area → HTTP adresi | `idx_speaker_zones_area` (002:43) | — |
| `library_objects`, `library_object_photos` | 003:24, 003:35 | nesne kütüphanesi | `idx_library_object_photos_object` (003:43) | `object_id` → library_objects CASCADE (003:38) |
| `library_object_diagnosis` | 004:32 | teşhis önbelleği | — | → library_objects CASCADE (004:34) |

Toplam 6 indeks (`grep -n 'CREATE INDEX' backend/sema/*.sql`). 005'in `DALSAN-SEMA:
YABANCI-ANAHTAR-KAPALI` işaretinin (005:29) sebebi `events.rule_id` SET NULL'dur: `DROP TABLE
rules` yabancı anahtar açıkken tüm olayların kural bağlantısını siler (005:14-19). Aynı tuzak
`zones` yeniden kurulursa `rules.zone_id` CASCADE üzerinden kuralları siler (R24).

### 4.6 Arayüz

Jinja2 + sade JS; 28 şablon, 11 kendi JS/CSS/SVG dosyası + `vendor/` (Inter, Lucide). Canlı
görüntü 1–2 sn aralıklı JPEG yoklamasıdır (`static/onizleme.js`), video akışı değil. Bölge
editörü `static/kamera_detay.js` (yalnız fare olayları, R35).

**Rota envanteri:** 15 router, 72 rota: 70 `@router` + 2 `@acik_router` (`/favicon.ico`, `/saglik`;
`rotalar.py:113`, `:129`) (`grep -c '@\(router\|acik_router\)\.\(get\|post\)' backend/app/web/*.py`).
HTML sayfası döndüren 23 GET:

| Kabuk | Sayfalar | AUDIT-OLCUM §2.2'de 200 |
|---|---|---|
| Eski kabuk (`temel.html`) | `/`, `/kameralar`, `/kameralar/yeni`, `/kameralar/{id}`, `/kurallar`, `/kurallar/yeni`, `/kurallar/{id}/duzenle`, `/olaylar`, `/olaylar/{id}`, `/kkd`, `/anons`, `/videolar` | `/`, `/kameralar`, `/kurallar`, `/olaylar`, `/kkd`, `/anons`, `/videolar` |
| Kabuksuz (`giris.html`) | `/giris` | — |
| Komuta kabuğu (`komuta_temel.html`) | `/komuta`, `/komuta/kilavuz`, `/komuta/duvar`, `/komuta/inceleme`, `/komuta/saglik`, `/komuta/uyari`, `/komuta/anons`, `/komuta/rapor`, `/nesneler`, `/ayarlar` | `/komuta`, `/komuta/saglik`, `/komuta/anons`, `/komuta/uyari`, `/komuta/rapor`, `/nesneler` |

Sayfa dışı uçlar: `/saglik` (JSON), `/olaylar/akis` (SSE), `/kameralar/{id}/durum.json`,
`/kameralar/{id}/onizleme.jpg`, `/goruntuler/{yol}`, `/kkd/ornek/{id}.jpg`, `/nesneler/foto/{ad}`,
`/nesneler/tarama-foto/{ad}`, `/olaylar/disa-aktar.csv`, `/komuta/rapor/ozet.csv`,
`POST /kameralar/{id}/alan-bul` (JSON). Kalan POST'lar form eylemleridir. `/komuta/duvar`,
`/komuta/inceleme`, `/komuta/kilavuz`, `/ayarlar`, `/giris` ve parametreli sayfalar ölçüm
koşusunda istenmedi; testlerde var (`test_komuta_pano_ve_duvar.py`,
`test_komuta_inceleme_ve_saglik.py`, `test_ayarlar_sayfasi.py`, `test_giris.py`).

- **`/nesneler`** (`nesne_rotalari.py:37-227`): kullanıcı nesnesini 2+ fotoğrafla tanıtır, sonra
  yüklediği fotoğrafta kayan pencereyle arar. Canlı analize girmez (`uygulama.py:128-131`).
  Tarama iş parçacığı havuzunda çalışır (`:289`); fotoğraf kaydı değil (R22).
- **`POST /kameralar/{id}/alan-bul`** (`alan_rotalari.py:50`): yüklenen ekran görüntüsünde ya da
  canlı karede (`_canli_kare:184`) zemin boyasından bölge önerisi döner (JSON). Görüntü diske
  yazılmaz (`uygulama.py:112-113`); `alan_bulucu` havuzda çalışır (`:94`, `:111`).
- **Kimlik:** tek `YONETICI_SIFRESI` (varsayılan boş, `.env.example:107`); boşken hiçbir sayfa
  giriş sormaz, doluyken 13 korumalı router'ın hepsi `oturum_gerekli` ister (`uygulama.py:97-135`).
  Korumasız olanlar: `/giris`, `/saglik`, `/favicon.ico` (`uygulama.py:101-106`) ve `/static`
  (`:137`). Oturum 12 sa (`giris.py:46`), kilit 5 deneme / 300 sn (`:51-52`, XFF sorunu R7).
  FastAPI `/docs` durumu DOĞRULANMADI (§11 #15).

## 5. Testler

**Envanter:** `tests/` altında 50 `test_*.py`. `tests/rules/` altında 8 test dosyası + `yardimci.py`
(testsiz), toplam 85 test fonksiyonu: `test_bolge_ihlali.py` 10, `test_hiz.py` 17,
`test_kalibrasyon.py` 4, `test_kkd.py` 13, `test_mesafe.py` 7, `test_motor.py` 8,
`test_saflik.py` 11 (`:105-183`), `test_sayim.py` 15 (`grep -c '^def test_'`; `parametrize` ve
`skip` yok). `tests/nesne_kiyas/` kalite kapısının takımıdır. `tests/hiz_kiyas/` hız takımıdır;
pytest kapısı değildir (içinde `test_*.py` yok, yalnız `__init__.py` + `__main__.py`), elle
`python -m tests.hiz_kiyas` ile koşulur (AUDIT-OLCUM başı). pytest `testpaths = ["tests"]`
(`pyproject.toml:5`).

**Alan → test dosyası:**

| Alan | Dosyalar (test sayısı) |
|---|---|
| Kural motoru (saf) | `tests/rules/*` (85) |
| Tespit / takip / hat | `test_tespit_sonisleme` (9), `test_boru_hatti_sayimi` (20), `test_analiz_entegrasyon` (2), `test_kamera_kaynagi` (10), `test_yaya_yolu_ve_kalite` (14) |
| Bölge / alan / çizim | `test_alan_bulucu` (13), `test_alan_bulma_rotasi` (10), `test_alan_cizimi_ve_sayim_arayuzu` (17), `test_bolge_cizim_katmani` (9), `test_bolge_cizim_kolayligi` (22), `test_bolge_duzenleme` (16), `test_cizim_kipi` (9), `test_hazir_kurallar` (12) |
| Kamera / kural / video | `test_kameralar` (15), `test_kurallar` (9), `test_video_yukleme` (22) |
| Olay / KKD / rapor | `test_olaylar` (11), `test_kkd_etiketleme` (3), `test_rapor` (25) |
| Anons / ses / Bluetooth | `test_ses_cikisi` (22), `test_anons_baglama` (15), `test_uyari_ve_anons` (15), `test_komuta_uyari_ve_anons` (39) |
| Komuta ekranları / arayüz | `test_komuta_kabugu` (11), `test_komuta_pano_ve_duvar` (17), `test_komuta_inceleme_ve_saglik` (27), `test_kilavuz_ve_kurulum` (38), `test_ana_sayfa` (4), `test_arayuz_varliklari` (17), `test_arayuz_surumu_ve_model_mesaji` (9), `test_dar_ekran_tasmasi` (5), `test_gorunen_model_adi` (15), `test_model_hatasi_ekranda` (4) |
| Nesne kütüphanesi | `test_nesne_kutuphanesi` (40), `test_nesne_teshisi` (62), `test_nesne_kiyas_kapisi` (15) |
| Kimlik / ayarlar | `test_giris` (29), `test_ayarlar` (9), `test_ayarlar_sayfasi` (22) |
| Veri / zaman / günlük | `test_veritabani` (12), `test_bakim_ve_zaman` (5), `test_zaman` (6), `test_gunluk_ayrintisi` (8) |
| Masaüstü / paketleme | `test_paketleme` (49), `test_mac_uygulamasi` (26), `test_paketlemeye_hazirlik` (16), `test_platform_uyumu` (17), `test_uygulama_penceresi` (16), `test_guncelleme` (12), `test_yedek_geri_yukleme` (11) |

(Sayılar `grep -c '^def test_'`; parametrize edilen testler pytest'te birden çok sayılır.)

**Ayrı `tests/rules` koşusu:** önceki envanterde "`pytest tests/rules -q` → 85 passed in 0.26s"
yazıyordu, ama bu koşunun çıktı dosyası yok (`tasks/` içinde `85 passed` geçen dosya bulunmuyor);
DOĞRULANMADI. 85 testin geçtiği yine de tam paketten çıkar: aşağıda 0 başarısız var, 17
atlamanın hiçbiri `tests/rules`'ta değil.

**Tam paket, 1. koşu** (`tasks/by392r477.output`; ham çıktıdan):

```
=== ruff ===
All checks passed!                                   (:3-4)
...
1023 passed, 17 skipped, 2 warnings in 106.39s (0:01:46)   (:45)
PYTEST_EXIT=0                                        (:46)
```

| Toplam | Geçen | Başarısız | Atlanan | Uyarı | Süre |
|---|---|---|---|---|---|
| 1040 | 1023 | 0 | 17 | 2 | 106,39 sn |

- Koşu Python **3.11** venv'inde yapıldı (`:22` `.venv/lib/python3.11/...`; `.venv/pyvenv.cfg` `version = 3.11.15`), CLAUDE.md §4'ün 3.12'si altında değil (§11 #19).
- Başarısız test yok; bu yüzden başarısız test adı ve nedeni listesi boştur.
- En yavaş 5 (`:30-34`):
  1. 46,74 sn setup — `test_nesne_kiyas_kapisi.py::test_kirmizi_cizgi_kutuphane_ici_yanlis_isim_yazilmaz` (modül fixture'ı; paketin ~%44'ü)
  2. 5,83 sn — `test_nesne_kiyas_kapisi.py::test_takimda_ayni_renkte_duz_yabanci_var`
  3. 5,58 sn — `test_analiz_entegrasyon.py::test_video_kaynagi_cevrimici_olur_ve_onizleme_gelir` (gerçek analiz iş parçacığı, sentetik mp4)
  4. 3,11 sn — `test_nesne_kiyas_kapisi.py::test_olcum_gercek_taramayla_ayni_sonucu_verir`
  5. 3,00 sn — `test_kamera_kaynagi.py::test_dongu_kipinde_video_basa_sarar`
- 17 atlama: PyInstaller kurulu değil (denetim `conftest.py:55`, gerekçe metni `:68-69`) → tarif koşturan fixture'lar `pytest.skip` çağırır (`test_paketleme.py:97-98`, `:107-108`; `test_mac_uygulamasi.py:58-59`). Dağılım: `test_mac_uygulamasi.py` 5, `test_paketleme.py` 12 (çıktıdaki `:14` ve `:17` satırlarındaki `s` kümeleri; dosya eşlemesi pytest'in alfabetik toplama sırasından çıkarım).
- 2 uyarı (`:22-26`): starlette testclient/httpx ve anyio `BlockingPortal` kullanım dışı bildirimi.

**Tam paket, 2. koşu (push öncesi):** iş akışı bildirimine göre `tests/hiz_kiyas` eklendikten
sonra tam paket yeniden koşuldu: 1023 geçti, 17 atlandı, ruff temiz. Bu koşunun ham çıktısı bu
rapora ulaşmadı; süre ve uyarı sayısı bilinmiyor. Sayının değişmemesi beklenendir, çünkü
`tests/hiz_kiyas/` pytest'in toplayacağı `test_*.py` içermez.

- Kapsam boşlukları: SSE `/olaylar/akis` ve `canli.js` hiç test edilmiyor; gerçek ONNX çıkarımı testte yok (`Tespitci.__new__`, sahte `onnxruntime`); `Takipci` doğrudan test edilmiyor; doğruluk (recall/mAP) ölçen test yok; `tests/fixtures/` yok; ses/Bluetooth yolu yalnız sahte `subprocess` ile sınanıyor (§4.2).

## 6. Donanım keşfi

**Bu konteyner — hedef donanım DEĞİLDİR:**

| Bileşen | Değer |
|---|---|
| Python | 3.11.15 (`.venv/pyvenv.cfg`; `tasks/bkf4oi06k.output`) |
| CPU | 4 **sanal** CPU (KVM konuğu; çekirdek başına 1 iş parçacığı, soket başına 4 çekirdek), Intel Xeon @ 2.10 GHz. Host'un fiziksel çekirdek sayısı bu konteynerden görülemez |
| RAM | 15 GiB (`free -h`; `MemTotal 16481980 kB`), swap yok |
| Disk | kök dosya sistemi 252 G, 27 G boş (`df -h`); AUDIT-OLCUM §2.1'deki bakım satırı "boş disk 27.4 GB" ile tutarlı |
| GPU | yok; `nvidia-smi` yok; ORT sağlayıcıları Azure+CPU (AUDIT-OLCUM §1) |
| Ses/Bluetooth | `bluetoothctl`, `aplay`, `pactl`, `paplay` yok |
| ffmpeg | sistem ikilisi yok (OpenCV kendi FFmpeg'ini taşır; uyumluluk avcısının bulgusu) |
| Docker | `Docker version 29.3.1, build c2be9cc` (`docker --version`); imaj derlenmedi |

Ham çıktılar (22 Eyl 2026, bu konteyner; `lscpu` çıktısı kısaltıldı):

```
$ for c in nvidia-smi lscpu bluetoothctl aplay pactl paplay ffmpeg docker; do printf "%s: " $c; command -v $c || echo "YOK"; done
nvidia-smi: YOK
lscpu: /usr/bin/lscpu
bluetoothctl: YOK
aplay: YOK
pactl: YOK
paplay: YOK
ffmpeg: YOK
docker: /usr/bin/docker
$ lscpu
Architecture:          x86_64
CPU(s):                4
On-line CPU(s) list:   0-3
Model name:            Intel(R) Xeon(R) Processor @ 2.10GHz
Thread(s) per core:    1
Core(s) per socket:    4
Socket(s):             1
Hypervisor vendor:     KVM
Virtualization type:   full
L3 cache:              260 MiB (1 instance)
$ free -h
               total        used        free      shared  buff/cache   available
Mem:            15Gi       787Mi        12Gi        12Mi       2.9Gi        14Gi
Swap:             0B          0B          0B
$ df -h /home/user/dalsan
Filesystem      Size  Used Avail Use% Mounted on
/dev/vda        252G   11G   27G  30% /
$ docker --version
Docker version 29.3.1, build c2be9cc
```

`nvidia-smi`, `bluetoothctl --version` ve `aplay -l` komutları bu konteynerde bulunmadığı için
çıktıları yok.

**Fabrika sunucusu** (`docs/05-TEKNOLOJI-KARARLARI.md:37-55`, §3, 3-4 kamera MVP):

| Bileşen | Gereksinim |
|---|---|
| GPU | NVIDIA ≥ 8 GB (RTX 4060 / 4060 Ti / T4 sınıfı) |
| CPU | ≥ 6 çekirdek |
| RAM | ≥ 16 GB |
| Disk | ≥ 512 GB SSD |
| Ağ | Kamera VLAN'ı + anons altyapısına erişim, NTP |
| Bütçe | 4 kamera × 6 fps = 24 çıkarım/sn, 640 px |
| Ses donanımı (ses kartı, amfi, Bluetooth adaptörü/hoparlör: model, adet, mesafe) | **operatör dolduracak** (`GOREV-TANIMI-V2.md:30`); DOĞRULANMADI |
| Sunucu işletim sistemi, Python sürümü, GPU modeli | Ubuntu + Docker öngörülüyor (`GOREV-TANIMI-V2.md:27`); gerçek makine DOĞRULANMADI (§11 #3) |

Not: docs/05 §3 "CPU-only ~1-2 fps" der (`docs/05:52-53`); ölçüm bunu modele bağlı kılar
(4 kamera benzetiminde kamera başına `tiny` 6,0 fps, `s` 2,4 fps — AUDIT-OLCUM §1.2 tablosu,
yorumu §1.3 #1). GPU'lu sunucu satın alınsa bile bugünkü imaj GPU'yu kullanamaz (§7, R3).
Fabrika container'ında ses/Bluetooth yolu da yok (§4.2, R36).

## 7. Teknik borç ve riskler

### 7.1 Bulgular (önem sırasıyla)

| # | Önem | Dosya:satır | Sorun | Öneri |
|---|---|---|---|---|
| R1 | yüksek | `analiz/kkd_siniflandirici.py:54-59` | Model yok → gözlem yok → `ppe_violation` sahada hiç olay üretmez; model verilirse `NotImplementedError` → `supervizor.py:529-532` her kareyi atar | ONNX sınıflandırıcı + `.env` model anahtarı; `supervizor.py:90` sabitini kaldır |
| R2 | yüksek | `analiz/tespit.py:31-36` | car/bus/truck → "truck"; forklift üretilmez; binek araç mesafe/hız kurallarına girer | Saha verisiyle ince ayar; sınıf eşlemesini tek kaynağa bağla |
| R3 | yüksek | `backend/requirements.txt:21`, `Dockerfile:18` | Yalnız CPU `onnxruntime`; compose GPU bloğu (`docker-compose.yml:37`) açılsa da GPU kullanılamaz (AUDIT-OLCUM §1.3-4) | Ayrı GPU imajı + `onnxruntime-gpu` (CPU paketiyle aynı ortama değil) |
| R4 | yüksek | `analiz/kamera.py:279` | `read()` zaman aşımsız; FFmpeg seçeneği yalnız `rtsp_transport;tcp` (`:38`); donan akışta iş parçacığı takılır, yeniden bağlanmaz | Açılış/okuma zaman aşımı + süpervizörde bekçi |
| R5 | yüksek | `analiz/supervizor.py:209-221` | Bekçi yok: DB açılamazsa analiz iş parçacığı biter; `/saglik` yine `analiz:true` (`rotalar.py:139`) | `is_alive()` denetimi, yeniden kurma, readiness ucu |
| R6 | yüksek | `analiz/takip.py:32` | ByteTrack yalnız `frame_rate` ile kurulur; gerisi supervision 0.25.1 varsayılanıdır (`.venv/lib/python3.11/site-packages/supervision/tracker/byte_tracker/core.py:42-46`): `track_activation_threshold=0.25`, `lost_track_buffer=30`. Formüller: `max_time_lost = int(frame_rate / 30 × lost_track_buffer)` (`:53`) → 6 fps'te int(6/30×30) = 6 kare = ~1 sn hafıza; `det_thresh = track_activation_threshold + 0.1` (`:52`) = 0,35, yani insan eşiği 0,28'in (`ayarlar.py:294`) üstünde: 0,28–0,35 güvenli insan yeni iz başlatamaz. Sonuç: 1 sn'den uzun örtülmede yeni ID, cooldown sıfırlanır, tekrar uyarı | `lost_track_buffer = 30 × hafıza_sn` (fps'ten bağımsız), activation eşiğini insan eşiğiyle hizala, `.env`'e taşı |
| R7 | yüksek | `web/giris.py:94-97` | Kilit adresi koşulsuz `X-Forwarded-For`'dan; her denemede sahte başlıkla 5 deneme/300 sn kilidi atlanır | `istek.client.host`; vekil için `--forwarded-allow-ips` |
| R8 | yüksek | `web/giris.py:146`, `uygulama.py:104` | CSRF/Origin/Host denetimi yok; şifresizken herhangi bir web sayfası `/ayarlar/kaydet` ile `SUNUCU_ADRESI`+şifre yazdırabilir | Origin/Sec-Fetch-Site middleware, host allowlist |
| R9 | yüksek | `web/templates/komuta_ayarlar.html:48`, `ayar_rotalari.py:96-99` | `YONETICI_SIFRESI` `<input type="text" value=…>` ile düz basılır | `type=password`, değer basılmaz, boş = değişmez |
| R10 | yüksek | `masaustu/dalsan_launcher.py:209` | Python üst sınırı yok; `onnxruntime==1.19.2`'nin cp313/cp314 tekerleği yok (avcının PyPI sorgusu) → "İlk Kurulum" pip'te kırılır | `(3,11) <= v < (3,13)`; .bat/.command'da da |
| R11 | orta | `analiz/supervizor.py:541-546, 623, 686` | JPEG kodlama, dosya yazma, commit tek analiz iş parçacığında; bakım aynı DB'ye yazar, `busy_timeout=5000` → tüm kameralar kör kalabilir | Yazıcı kuyruğu + ayrı işçi |
| R12 | orta | `analiz/supervizor.py:677` | `measured_fps` okuma hızıdır (`kamera.py:312-315`); işlenen kare/gecikme ölçülmez; kılavuz "işlenen" der (`kilavuz.py:71-72`) | İşlenen fps + `isle()` süresi sayacı |
| R13 | orta | `Dockerfile:40` | `--host 0.0.0.0` sabit; `SUNUCU_ADRESI` emniyet kilidi (`ayarlar.py:222`) container'da işlemez; port satırı değişirse şifresiz LAN'a açılır | Container'da şifre zorunlu ya da entrypoint `.env`'den host okusun |
| R14 | orta | `ayarlar.py:407-410` | `_env_degeri` `\n`/`\r` kontrol etmiyor → `.env` satır enjeksiyonu (`anons_web.py:100` doğrulamasız); çalıştırılarak DOĞRULANMADI | Kontrol karakterlerini reddet; anahtar allowlist |
| R15 | orta | `web/giris.py:197` | `hmac.compare_digest(str,str)` ASCII dışı karakterde `TypeError` → Türkçe karakterli şifreyle giriş 500 (Python belgesine dayanır, DOĞRULANMADI) | Bayt karşılaştır |
| R16 | orta | `web/giris.py:62-63` | Çerez HMAC anahtarı yalnız şifreden; çevrimdışı kırılabilir; `/cikis` sunucu tarafında iptal etmez | Kuruluma özgü rastgele sır |
| R17 | orta | `analiz/model_indir.py:79-85`, `:22`, `:69`; `models/indir.sh:10-15` | Tek içerik denetimi ≥1 MiB; `Content-Length` okunur ama karşılaştırılmaz; `BILINEN_MODELLER` özetsiz ad listesi; `hashlib` yok; `indir.sh`'de boyut denetimi bile yok (§3) | `BILINEN_MODELLER`'i {ad: sha256} yap, iki yolda da doğrula |
| R18 | orta | `web/templates/kamera_detay.html:320`; `olaylar/anons.py:217` | RTSP şifresi düzenleme formunda açık; HTTP anons adresi (kimlik dahil) günlüğün `mesaj` alanına | Maskeli form; maskeli log |
| R19 | orta | `analiz/supervizor.py:329-341` | Damgada `announcement_messages` yok → mesaj/WAV değişikliği canlıya inmez; "Dene" taze satırı kullanır | Tabloya `updated_at` + damgaya ekle |
| R20 | orta | `olaylar/anons.py:331`, `:313` | Thread-per-call, kuyruk/öncelik/kilit yok; cooldown (kamera, mesaj) başarısız çalmada da tüketilir | Tek işçi + öncelik kuyruğu, hedef bazlı cooldown |
| R21 | orta | `rules/mesafe.py:30-34, 60` | Pasif bölge denetlenmez; kayıp toleransı yok; `hiz_mps=None` "duruyor" sayılır | Diğer kurallarla hizala |
| R22 | orta | `web/olaylar_web.py:111`; `web/videolar.py:264`; `web/alan_rotalari.py:62`; `web/nesne_rotalari.py:126`, `:165`, `:173`; `web/ayar_rotalari.py:393` | `async` gövdede senkron I/O → olay döngüsü bloklanır. SSE sorgusu, video diske yazımı, `alan_bul`'daki SELECT, `depo.fotograf_ekle` (SELECT `depo.py:77` + `write_bytes` `:85` + `cv2.imread` `:93` + INSERT `:99`), `depo.nesne_ekle`, `depo.nesne_sil`, `.env` yazımı. Ağır işler zaten havuzda: `alan_bulucu` (`alan_rotalari.py:94`, `:111`), tarama (`nesne_rotalari.py:289`), kural kaydı (`kurallar.py:118`) | Kalanları da `run_in_threadpool`'a al ya da gövdeyi `def` yap |
| R23 | orta | `olaylar/yazici.py:107`; `supervizor.py:600-638, 788-810` | KVKK: kanıt ve kırpıklar ham; etiketli kırpıklar süresiz; `veri/videolar`, `veri/nesneler` bakım dışı | Bulanıklaştırma, saklama politikası |
| R24 | orta | `sema/001_ilk.sql:50-52, 105-106`; `sema/005:48-49` | Tip/durum listeleri CHECK'e gömülü; yeni bölge tipi/olay durumu = tablo yeniden kurma + `rules.zone_id` CASCADE tuzağı | 005 deseni + işaret satırı ya da CHECK → Pydantic |
| R25 | orta | `web/kurallar.py:285-318`; `kural_form.html:168` | Form varsayılanları `parametreler.py`'nin ikinci kopyası; cooldown her tipte 120 önceden dolu (docs/03: 90/180) | Şemadan türet |
| R26 | orta | `docs/06-OPERASYON.md:83` | systemd `ExecStart … app.main:uygulama`; modülde sembol `app` (`main.py:63`) | `app.main:app` |
| R27 | orta | `docker-compose.yml:24` | `.env` `:ro` bind mount; `env_dosyasina_yaz` `replace()` Docker'da başarısız olur (DOĞRULANMADI) | Belgele ya da dizin bağla |
| R28 | düşük | `analiz/supervizor.py:113` | `_canli_sayim.values()` kilitsiz; analiz iş parçacığı sözlüğü değiştirirse `RuntimeError` | `list(...)` kopyası |
| R29 | düşük | `analiz/supervizor.py:528` | Kurala `kare_zamani` yerine `simdi` gider → hız `dt` sapar | `kare_zamani` geçir |
| R30 | düşük | `web/hoparlorler.py:41` | Hedef sınırsız sunucu isteği (SSRF), hata metni ekrana | Loopback/link-local reddi |
| R31 | düşük | `web/olaylar_web.py:156`; `web/rapor.py:391-400` | CSV formül enjeksiyonu kaçışı yok | Hücre ön eki |
| R32 | düşük | `Dockerfile:10-14` | Root kullanıcı; `ffmpeg` apt paketi gereksiz (cv2 kendi FFmpeg'ini taşır) | `USER`, satırı çıkar |
| R33 | düşük | `backend/requirements.txt:3-10, 22` | Web yığını ve numpy sabitsiz; pytest/httpx/ruff fabrika imajına kurulur | Lock/üst sınır, dev dosyası |
| R34 | düşük | `analiz/supervizor.py:406-410` | `sample_fps` değişince hat sıfırlanır: takip, cooldown, sayaçlar gider | Takipçiyi yeniden kurmadan fps güncelle |
| R35 | düşük | `static/kamera_detay.js` | Yalnız fare olayları; dokunmatik/pointer yok | Pointer events |

Düzeltme turunda eklenenler (önem sırasına yerleştirilmedi):

| # | Önem | Dosya:satır | Sorun | Öneri |
|---|---|---|---|---|
| R36 | yüksek (DOĞRULANMADI) | `Dockerfile:10-12`; `docker-compose.yml:47-50`; `olaylar/anons.py:84-89`, `:117-127` | Fabrika container'ında ses aracı yok (`aplay`/`paplay`/`pactl`); compose yalnız `/dev/snd` (ALSA) öneriyor, PulseAudio/PipeWire soketi ve BlueZ D-Bus bağlanmıyor, ALSA Bluetooth'u görmüyor → `ANONS=ses_karti` ve Bluetooth hoparlör container'da çalışamaz; ekran yalnız "ses çalma komutu bulunamadı" der. İmaj derlenmedi | Kararı belgele: ya imaja `pulseaudio-utils` + host'un Pulse/PipeWire soketini bağla, ya sesi host'taki küçük bir çalıcıya HTTP anonsla ver |
| R37 | orta | `olaylar/ses_cihazlari.py:105-106`; `templates/anons.html:59` | Seçim boşken `cihaz_bagli_mi('')` hep True; Mac/Windows'ta seçim hiç yapılamadığı için Bluetooth kopması bu platformlarda (ve Linux'ta varsayılan çıkışta) hiç algılanmaz | Varsayılan çıkışın kendisini izle (Linux `get-default-sink`, macOS varsayılan işareti); öğrenilemiyorsa None |
| R38 | düşük | `templates/anons.html:47-49` | Liste okunamazsa (None) seçili cihaz için yeşil "bağlı" rozeti basılır; üç durumlu tasarım (`ses_cihazlari.py:99-103`) ekranda iki duruma iner | None için ayrı "bilinmiyor" rozeti |
| R39 | düşük | `uygulama.py:94`; `web/anons_web.py:100`, `:119`; `templates/anons.html:31-32` | Ses çıkışı kaydı bellekteki ayarı güncellemez: yeniden başlatılana kadar test sesi eski çıkışa çalar, sayfa eski seçimi gösterir; "başka çıkış seçip tekrar deneyin" yönlendirmesi yanıltıcı (kod okuması, DOĞRULANMADI) | Kayıttan sonra ayarı yeniden yükle ya da test sesine formdaki çıkışı geçir |
| R40 | düşük | `templates/komuta_anons.html:34`; `web/anons_web.py:69-72` | Komuta anons ekranı ses çıkışı/Bluetooth durumunu göstermiyor; docstring gösterilmesi gerektiğini söylüyor (§10) | `ses_cikisi_baglami`'nı `anons_baglami`'na ekle |
| R41 | düşük | `static/uyari.js:67`, `:77` | Boş `catch`: bip ve seslendirme hatası iz bırakmaz (CLAUDE.md §7'nin JS karşılığı) | Ekranda "sesli uyarı çalışmıyor" satırı ya da `console.warn` |

### 7.2 Sabit kodlanmış eşikler (CLAUDE.md §7 ile gerilim)

| Dosya:satır | Değer | Anlam |
|---|---|---|
| `analiz/kamera.py:47-48` | 1,0 / 30,0 sn | yeniden bağlanma ilk/tavan |
| `analiz/kamera.py:50` | 60 sn | offline eşiği (`CAMERA_DOWN` 10 sn ister) |
| `analiz/kamera.py:52` | 3 sn | TCP ön kontrol |
| `analiz/boru_hatti.py:49` | 5 | KKD kare aralığı |
| `analiz/boru_hatti.py:106` | 3 | sayım kararlılık karesi |
| `analiz/boru_hatti.py:171` | % 50 | kalite ölçüm kadansı |
| `analiz/goruntu.py:31-34` | 55/205/40/22 | kalite teşhis eşikleri |
| `analiz/tespit.py:266` | × 0,9 | NMS skor eşiği çarpanı |
| `analiz/takip.py:32` | 0,25 / 30 (varsayılan) | ByteTrack activation / lost buffer |
| `rules/bolge_ihlali.py:20`, `hiz.py:41`, `sayim.py:40` | 5 | kayıp toleransı (üç kopya) |
| `rules/kkd.py:25` | 2 px | kesik kutu payı |
| `rules/motor.py:39-40` | 0,05 / 5,0 sn | hız `dt` aralığı |
| `analiz/supervizor.py:48-50` | 5 / 5 / 86400 sn | konfig / durum / bakım |
| `olaylar/anons.py:143`, `:210` | 20 / 5 sn | ses / HTTP zaman aşımı |
| `analiz/model_indir.py:79` | 1 MiB | model indirme boyut eşiği |
| `web/giris.py:46, 51-52` | 12 sa / 5 / 300 sn | oturum / deneme / kilit |
| `loglama.py:85, 98` | INFO / 5 MB × 3 | log seviyesi / dönüş |
| `veritabani.py:68` | 5000 ms | `busy_timeout` |
| `web/kameralar.py:98, 506` | `Form(6)`, 0,5–30 | `.env KARE_ORNEKLEME_FPS` okunmaz |
| `nesneler/kutuphane.py:189` | 0,24 | `ayarlar.py:329` varsayılanının kopyası |
| `analiz/alan_bulucu.py:45-85` | 12 modül sabiti | 4 HSV bant sınırı (`_SARI_ALT/UST` `:45-46`, `_BEYAZ_ALT/UST` `:50-51`) + 7 oran/sayı eşiği (`_KAPAMA_ORANI` `:56`, `_EN_KUCUK/_EN_BUYUK_ALAN_ORANI` `:60-61`, `_SADELESTIRME_ORANI` `:65`, `_EN_COK_KOSE` `:69`, `_GRUP_MESAFE_ORANI` `:77`, `_EN_AZ_GRUP_PARCASI` `:81`) + işleme genişliği 960 px (`_ISLEME_GENISLIGI` `:85`; eşik sayılmaz) |

Kodda gömülü şifre/API anahtarı yok (sır avcısı taraması); `.env` okuma yalnız `ayarlar.py`'de.

### 7.3 Bellek sızıntısı adayları

7x24 çalışmada takip kimliğiyle ya da istekle büyüyen yapıların taraması (kod okuması; bellek
ölçülmedi, DOĞRULANMADI):

| Yer | Yapı | Budama | Sonuç |
|---|---|---|---|
| `rules/cooldown.py:14` | `_son` (kural, kamera, takip) → zaman | `temizle()` her değerlendirmede, eşik `max(3600 sn, 2 × en uzun cooldown)` (`motor.py:131`) | aday değil |
| `rules/motor.py` | `_son_konumlar` (takip → konum) | 60 sn'den eskiler atılır (`motor.py:152-155`) | aday değil |
| `rules/kkd.py:33` | `_durumlar` (takip → pencereler) | `10 × window_size` değerlendirme görülmeyen silinir (`kkd.py:75-83`); pencere `deque(maxlen)` (`:59`) | aday değil |
| `rules/mesafe.py:22` | `_ardisik` (çift → sayaç) | aktif olmayan çiftler silinir (`mesafe.py:88-91`) | aday değil |
| `rules/bolge_ihlali.py:27-28`, `rules/hiz.py:48-49` | takip başına giriş/kayıp/ölçüm | kayıp toleransı (5) aşılınca silinir (`bolge_ihlali.py:78-85`, `hiz.py:104-111`); hız penceresi kırpılır (`hiz.py:76`) | aday değil |
| `rules/sayim.py:82-90` | bölge → takip sayaçları | kayıplar (`:195-201`), sayılmış kimlik üst sınırı 20 000/bölge (`:45`, `:204-216`), silinen bölge (`:218-222`) | aday değil (üst sınırlı) |
| `analiz/boru_hatti.py:135` | `_kkd_sayac` | ekranda olmayan takipler atılır (`:298`); model yokken hiç dolmaz (`:293`) | aday değil |
| `analiz/boru_hatti.py:153` | `_jpeg_onbellek` | anahtar `bool`, en çok 2 giriş | aday değil |
| supervision `ByteTrack` | `removed_tracks` | her güncellemede yerine konur, birikmez (`core.py:308`) | aday değil |
| `analiz/supervizor.py:60-82` | kamera başına sözlükler | kamera silinince/pasifleşince `_kaynaklar`, `_kaynak_damgalari`, `_hatlar`, `_kamera_konfig`, `_son_durumlar`, `_canli_sayim` temizlenir (`:426-433`); `_siradaki_ornek`, `_son_islenen_kare`, `_son_kkd_ornek` (`:68-70`) **temizlenmez** | zayıf aday: kamera id başına bir float, oluşturulan kamera sayısıyla sınırlı; pratik etkisi yok |
| `olaylar/anons.py:289` | `AnonsYoneticisi._cooldown` | `temizle()` hiç çağrılmaz (tek kullanım `:314`) | zayıf aday: anahtar (kamera, mesaj), kamera × mesaj ile sınırlı |
| `olaylar/anons.py:331` | anons başına daemon iş parçacığı | çalma bitince biter (ses 20 sn `:143`, HTTP 5 sn `:210` zaman aşımı); (kamera, mesaj) başına 30 sn cooldown sayıyı sınırlar; "Dene" düğmesi cooldown'suz (`:318-319`) | sızıntı değil; kuyruksuz eşzamanlılık R20 |
| `web/olaylar_web.py:103-136` | SSE üreteci | açık sekme başına bir SQLite bağlantısı; kopuş her saniye yoklanır (`:109`), `finally` kapatır (`:135-136`) | aday değil (istemci sayısıyla doğrusal) |
| `web/giris.py:59` | `_denemeler` (adres → deneme) | 1000 adresi aşınca en eski yarısı atılır (`:53-56`, `:121-123`) | aday değil; ama sahte XFF ile kayıt itilebilir (R7) |
| `analiz/takip.py:29` | `_bildirilen_bilinmeyenler` | sınıf adı kümesi | aday değil |
| `nesneler/arama.py:310` | tarama çıktısı JPEG'leri (disk) | en yeni 60 tutulur (`:65`, `:310-328`) | bellek değil; disk sınırlı |
| `veri/videolar`, `veri/nesneler`, etiketli KKD kırpıkları (disk) | yüklenen dosyalar | bakım döngüsüne girmez (R23; `depo.py:1-10`) | disk büyümesi adayı (bellek değil) |

## 8. §4 gereksinimlerine karşı boşluk haritası

Madde metinleri: `docs/GOREV-TANIMI-V2.md` §4; errata E1–E14 aynı belgenin Ek A'sındadır.

### 8.A Algılama, bölge, KKD, takip, kural (§4.1–§4.5)

| Gereksinim | Durum | Kanıt | Not |
|---|---|---|---|
| §4.1 `config/classes.yaml` | conflict | `config/` yok; `tipler.py:35` | E5: yaml yeni parça |
| §4.1 kapalı 7 sınıf, sabit id | partial | `tipler.py:35`; `takip.py:21` | 3 sınıf; id sıra türevi, kalıcı değil |
| §4.1 forklift/tır ayrı | partial | `tespit.py:31-36` | forklift yok; car+bus+truck birleşik |
| §4.2 6 bölge tipi | partial | `sema/001:50-52`; `ortak.py:17` | crossing, ppe_exempt yok |
| §4.2 `config/zones/*.yaml` | conflict | `sema/001:45`; E5 | SQLite `zones` |
| §4.2 0..1 normalize çokgen | exists | `kameralar.py:568-578` | |
| §4.2 arayüzde çiz/düzenle | exists | `kameralar.py:338-433` | dokunmatik yok |
| §4.2 ayak noktası | exists | `tipler.py:63-67` | |
| §4.2 boyadan öneri (v3) | partial | `alan_bulucu.py:123-124` | yalnız 2 tip; kod gereksinimin önünde |
| §4.3 üç durum | exists | `tipler.py:17-19`; `kkd.py:21` | |
| §4.3 unknown ≠ ihlal | exists | `kkd.py:128-129`; `test_kkd.py:68` | |
| §4.3 KKD sınıflandırıcı | missing | `kkd_siniflandirici.py:54-59` | olay üretilmez |
| §4.3 yöntem seçimi | partial | docs/04 §2; `boru_hatti.py:286` | iki aşama seçilmiş, 2. aşama yok |
| §4.3 unknown koşulları | partial | `kkd.py:105-117, 170-178` | görünürlük/bulanıklık yok; 120/80 px |
| §4.3 sürücü muafiyeti | missing | grep boş; docs/04 §5.3 | politika açık |
| §4.3 ppe_exempt dışında her yer | conflict | `kkd.py:36-38`; `boru_hatti.py:280` | dahil etme modeli + docs/08 R9 |
| §4.3 zor negatifler | partial | docs/04:134-146 | yalnız plan |
| §4.4 ByteTrack | exists | `takip.py:32` | |
| §4.4 kararlı track_id | partial | `takip.py:32`; `core.py:42-53` | ~1 sn hafıza |
| §4.4 iz bazlı pencere | exists | `bolge_ihlali.py:54-57`; `kkd.py:57-60` | mesafede tolerans yok |
| §4.5 `rules.yaml`, sabit yok | conflict | `parametreler.py`; E5 | eşikler DB'de; kalanlar §7.2 |
| §4.5 kural alanları | partial | `parametreler.py:25,34,50`; `tipler.py:92` | tek zone; severity ölü |
| §4.5 önem seviyeleri | partial | `tipler.py:97`; `supervizor.py:492` | hep "warning" |
| `PPE_NO_HELMET` | partial | `kkd.py:119-168` | tek ppe_violation; pencere ~12,5 sn = `window_size` 15 değerlendirme (`parametreler.py:48`) × KKD her 5. karede (`boru_hatti.py:49`) ÷ 6 fps; oran %75 = `violation_ratio` 0,75 (`parametreler.py:50`) |
| `PPE_NO_VEST` | partial | `kkd.py:100-117` | aynı |
| `PERSON_IN_VEHICLE_LANE` | partial | `bolge_ihlali.py:23-86` | elle; bağlamsal HIGH yok |
| `VEHICLE_ON_WALKWAY` | partial | `bolge_ihlali.py:39` | elle; forklift yok |
| `VEHICLE_PERSON_PROXIMITY` | partial | `mesafe.py:18-92` | 3 m var; CRITICAL yok |
| `RESTRICTED_ENTRY` | partial | `ortak.py:346` | varsayılan 2 s |
| `CAMERA_DOWN` | partial | `kamera.py:50`; `supervizor.py:662-669` | 60 s sabit |
| `AUDIO_CHANNEL_DOWN` | missing | `anons_web.py:81` | yoklama yok |
| homografi | exists | `kalibrasyon.py:19-53` | 4 nokta, SQLite |
| kalibrasyonsuz `confidence: low` | conflict | `mesafe.py:25-26`; docs/08:47 | bilinçli pasif |
| ACTIVE → RESOLVED | missing | `tipler.py:100-107` | anlık olay |
| iz bazlı cooldown | exists | `cooldown.py:16-22` | |
| histerezis | missing | `bolge_ihlali.py:48-52` | tek eşik |
| olay alanları | partial | `sema/001:95-109` | confidence/resolved_at/clip_path yok |
| olay klibi | conflict | ADR-009 `docs/05:105-108` | yalnız snapshot |

### 8.B Uyarı kanalları ve Bluetooth (§4.6)

| Gereksinim | Durum | Kanıt | Not |
|---|---|---|---|
| `AlertChannel` arayüzü | partial | `anons.py:46,103,224` | `name`≈`ad`; `health()` yok |
| öncelik kuyruğu | missing | `anons.py:331` | severity anonsa gitmez |
| aynı anda tek ses | missing | `anons.py:331` | kilit yok |
| dakikada N sınırı | missing | `ayarlar.py:314` | yalnız bekleme |
| aynı olay cooldown | partial | `anons.py:313-314` | global, (kamera, mesaj) |
| olay birleştirme | missing | `supervizor.py:540-541` | metin sabit |
| Türkçe WAV öncelikli | partial | `anons_web.py:150-154` | depoda WAV yok |
| çevrimdışı TTS | conflict | docs/14 §8; E3 | tarayıcı `uyari.js:70-78` |
| en az bir sağlıklı kanal | missing | `anons.py:360-366` | CRITICAL kaydı yok |
| eşzamanlı kanallar | missing | `ayarlar.py:28,233` | tek `ANONS` |
| `local_audio` | partial | `anons.py:60-100` | varsayılan `null`; fabrika container'ında çalıcı yok (R36) |
| `bluetooth_audio` | partial | `ses_cihazlari.py:53,113,177,200` | ses kartının çıkışı; tanıma Linux'ta sink adı, macOS'ta taşıma alanı + ad, Windows'ta yalnız ad (§4.2); container'da yol yok (R36) |
| `dashboard` | partial | `olaylar_web.py:98`; `uyari.js` | komuta ekranlarında yok |
| `webhook` imzalı | partial | `anons.py:172-221` | yük `{key,text}`, imza yok |
| `ip_speaker` SIP/ONVIF | conflict | docs/14 §8; E4 | HTTP var |
| `messaging` | missing | `komuta.py:844` | docs/07 #4 |
| `stack_light` | missing | grep boş | yol haritasında yok |
| BlueZ D-Bus A2DP | partial | `ses_cihazlari.py:142-158` | pactl üzerinden; D-Bus yok |
| Windows WASAPI | conflict | `ses_cihazlari.py:14-32, 68-74` | kütüphane bilerek yok |
| tara→eşleştir→bağlan | conflict | `docs/14:55`; E2 | OS'a bırakılmış |
| MAC `alerts.yaml` | conflict | `ayarlar.py:309`; E5 | `.env` sink adı |
| otomatik yeniden bağlanma | missing | `ses_cihazlari.py:98-110` | OS'a bırakılmış |
| 10 s sağlık kontrolü | partial | `anons_web.py:81` | yalnız `/anons` açılınca; seçim boşken hep "bağlı" (`ses_cihazlari.py:105-106`, R37); `/komuta/anons`'ta hiç yok (R40) |
| 30 s düşüş + olay | missing | `anons.py:150-155` | fallback yok |
| ses seviyesi | conflict | docs/14 §8 | bilerek yok |
| test sesi düğmesi | exists | `anons_web.py:104-122` | yalnız ses kartı yolu; yeni seçilen çıkışa restart'tan sonra çalar (R39) |
| gecikme ölçümü | missing | `anons.py:140-147` | ölçülmez |
| sınırlar belgesi | partial | docs/14:61-65 | menzil + metal raf uyarısı var; gereksinimdeki "~10 m" (`GOREV-TANIMI-V2.md:148`) ve motor gürültüsü etkisi yazılmamış |
| bölge başına cihaz | missing | `anons.py:338-349` | bölge yalnız HTTP |
| Bluetooth tek kanal olamaz | partial | `supervizor.py:546` | kodda zorlanmaz |

### 8.C Veri, model, metrik (§4.7–§4.8)

| Gereksinim | Durum | Kanıt | Not |
|---|---|---|---|
| mevcut veri/model değerlendirmesi | partial | `tespit.py:31-36`; AUDIT-OLCUM §1 | yalnız hız ölçülü |
| sınıf kapsamı | partial | `tespit.py:26-36` | loader/pallet_jack yok |
| eğitim hattı | missing | `egitim/` yok | docs/09 #7 uygulanmamış |
| açık veri lisansı | missing | grep boş; E1 | SH17 lisansı DOĞRULANMADI |
| saha verisi + `ANNOTATION.md` | partial | `supervizor.py:582-638` | ANNOTATION.md, kkd-politika.md yok |
| kamera/gün ayrımı | partial | docs/04:251-263; `sema/001:117-118` | kod yok |
| artırma | missing | docs/04:282-292 | yalnız plan |
| model adayı gerekçesi | partial | `tespit.py:1-5`; `docs/05:65-66` | doğruluk karşılaştırması yok |
| ONNX→TRT/OpenVINO/INT8 | missing | `tespit.py:86-90` | yalnız CPU/CUDA |
| model kayıt defteri | missing | `models/` düz; `model_indir.py:79` | sha256 yok |
| person recall ≥ 0,95 | missing | tests/ grep boş | ölçüm aracı yok |
| forklift/truck mAP50 | missing | `tespit.py:31-36` | forklift tanımsız |
| KKD precision ≥ 0,90 | partial | `olaylar_web.py:198-243`; `rapor.py:125-148` | veri kaynağı var, olay yok |
| KKD recall ≥ 0,85 | conflict | docs/04:376-378; E10 | taahhüt edilmez |
| gecikme ≤ 500 ms / 1 s | partial | `tests/hiz_kiyas`; AUDIT-OLCUM §1.3-6 | yalnız tespit adımı ölçüldü; AUDIT-OLCUM'daki "A2DP 100–250 ms" ölçüm değil, gereksinim belgesinin tipik değeridir (`GOREV-TANIMI-V2.md:147`) |
| ≥ 10 fps | partial | `kamera.py:312-315`; E14 | bütçe 6 fps; işlenen fps ölçülmez |
| yanlış alarm ≤ 2/sa/kamera | partial | `rapor.py:125-148` | oran var, saatlik yok |
| uptime ≥ %99,5 | missing | `rotalar.py:129-141` | geçmiş yok |
| tespit ölçüm takımı | partial | `tests/hiz_kiyas` | doğruluk takımı yok |
| KKD veri toplama | partial | `supervizor.py:582-638` | piksel eşiği yok, Rev.02 kapısı yok |
| etiketleme akışı | partial | `kkd_web.py:55-74` | dışa aktarım yok |
| gölge mod | exists | `supervizor.py:555-557`; `sema/002:55` | mekanizma var (kural başına `shadow_mode`). KKD için gölge mod (`docs/04:382-390`: 3 gün anonssuz, sonra precision) koşulamaz, çünkü model yok (`kkd_siniflandirici.py:54-59`); README'nin ⏳'ı (`README.md:55`) bu anlamda doğru (§10) |

### 8.D Güvenilirlik, KVKK, arayüz (§4.9–§4.11)

| Gereksinim | Durum | Kanıt | Not |
|---|---|---|---|
| kamera başına süreç | conflict | `supervizor.py:58`; E6 | TEK program kararı |
| supervisor + watchdog | partial | `supervizor.py:209-221` | bekçi yok |
| geri basınç | exists | `kamera.py:309`; `supervizor.py:522-524` | |
| RTSP üstel geri çekilme | partial | `kamera.py:47-48, 169-209` | okuma zaman aşımı yok |
| `/healthz` | partial | `rotalar.py:129-141` | her koşulda 200 |
| Prometheus | missing | grep boş; E7 | düz metin metrik yazılabilir |
| JSON günlük | exists | `loglama.py:45-62` | uvicorn logları düz |
| olay deposu SQLite | exists | `sema/001:95-109` | |
| olay klibi 5+5 s | conflict | ADR-009; docs/08:49 | Phase 2 |
| saklama 30 gün vars. | partial | `ayarlar.py:272-275` | vars. 180/90 |
| disk koruması | partial | `supervizor.py:742-753` | yalnız uyarı |
| NTP | missing | docs/08 R7 (`:13`) | docs/06'da yok |
| sıcak yükleme | partial | `supervizor.py:329-344` | `.env` restart ister |
| düzgün kapanış | partial | `supervizor.py:98-102` | bakım/anons beklenmez |
| systemd | partial | `docs/06:83` | yanlış sembol |
| Docker imajı | partial | `Dockerfile:3,40` | CPU-only, derlenmedi |
| `docs/KVKK.md` | missing | dosya yok; docs/00:78-107 | hukuk birimi kararı |
| yüz tanıma yok | exists | requirements; grep boş | |
| yüz bulanıklaştırma | missing | `yazici.py:107` | docs/07 #6 |
| rol tabanlı erişim | conflict | `giris.py:139-149`; docs/15 §7 | tek şifre; varsayılan boş (`.env.example:107`), yani kimlik varsayılan kapalı (§8.F) |
| klip denetim günlüğü | conflict | `olaylar_web.py:246-256`; docs/01:128 | kimlik yok |
| sırlar yalnız env | partial | `sema/001:21`; `anons.py:217` | RTSP şifresi DB'de |
| buluta veri yok | exists | `model_indir.py:21` tek dış bağlantı | |
| ham video yok | exists | ADR-009 | yüklenen videolar süresiz |
| canlı görüntü + katman | exists | `kameralar.py:319-332`; `boru_hatti.py:312` | JPEG yoklaması |
| bölge editörü | exists | `kamera_detay.js`; `kameralar.py:338-433` | |
| olay listesi + klip | partial | `olaylar_web.py:68-95` | klip yok |
| kamera sağlığı | exists | `komuta.py:756-828` | okuma fps'i |
| KKD uyum istatistikleri | partial | `rapor.py:201-269` | uyum oranı/vardiya yok |
| kanal ayarları + BT sayfası | conflict | `anons_web.py:37-101`; `docs/14:55` | eşleştirme bilerek yok |
| CSV / PDF | exists | `rapor.py:367-424`; `komuta_rapor.html` | PDF = tarayıcı yazdır |
| kullanıcı yönetimi | conflict | docs/15:187; docs/01:121 | FUTURE |
| REST + WebSocket | conflict | docs/01:94; ADR-005; E7 | SSE var |
| giden webhook | partial | `anons.py:172-221` | olay yükü/imza yok |
| MQTT | conflict | grep boş; E7 | yeni parça |

### 8.E Sayım

| Grup | exists | partial | missing | conflict | Toplam |
|---|---|---|---|---|---|
| A (§4.1–4.5) | 9 | 18 | 5 | 6 | 38 |
| B (§4.6) | 1 | 11 | 12 | 6 | 30 |
| C (§4.7–4.8) | 1 | 12 | 8 | 1 | 22 |
| D (§4.9–4.11) | 10 | 13 | 4 | 8 | 35 |
| **Toplam** | **21** | **54** | **29** | **21** | **125** |

### 8.F Ek satırlar (sayıma girmez)

§4'te ayrı madde olmayan, ama §4 maddelerinin sahada karşılanmasını belirleyen iki dağıtım
koşulu. 8.E'deki 125 madde sayımını değiştirmemek için ayrı tutuldu.

| Konu | Durum | Kanıt | Not |
|---|---|---|---|
| Fabrika container'ında ses/Bluetooth yolu (§4.6 `local_audio`/`bluetooth_audio` için ön koşul) | missing | `Dockerfile:10-12`; `docker-compose.yml:47-50`; `anons.py:84-89` | çalıcı araç, Pulse/PipeWire soketi ve BlueZ D-Bus yok; R36; imaj derlenmedi, DOĞRULANMADI |
| Kimlik varsayılan kapalı (§4.10 rol tabanlı erişimin ön koşulu) | partial | `.env.example:107` (`YONETICI_SIFRESI=`); `ayarlar.py:173-176`, `:211`; `uygulama.py:97-104` | şifre boşken hiçbir sayfa giriş sormaz; ağa açılırken (`SUNUCU_ADRESI`) şifre zorunlu (`ayarlar.py:222-230`), ama Docker bu kilidi atlar (R13); README "bilerek kapalı ⏳" derken docs/07 "Kapandı" der (§10) |

## 9. Yeniden kullanılabilir parçalar ve çakışanlar

### 9.1 v2 için olduğu gibi kalacaklar

- `analiz/kamera.py` KameraKaynagi: son-kare deseni, TCP ön kontrol, 1→30 sn geri çekilme, 4 durum, tek geçişlik video (yalnız okuma zaman aşımı eklenir).
- `rules/` tamamı: `tipler.py` sözleşmesi (ayak noktası, normalize poligon), `kkd.py` üç durumlu zamansal oylama, `cooldown.py`, `kalibrasyon.py` DLT homografi, `motor.py` imza tabanlı restart'sız yükleme, `parametreler.py` Pydantic şemaları, `tests/rules/test_saflik.py` AST bekçisi.
- `tespit.py` ön/son işleme matematiği ve CUDA→CPU düşüş uyarısı (`:120-132`).
- `olaylar/anons.py`: `http_gonder`/`_istek_hazirla` (webhook iskeleti), `_ses_komutu`, `bolge_sec`; `ses_cihazlari.py` (üç durumlu bağlılık = `health()` tabanı); `test_sesi.py`.
- `olaylar/yazici.py` fotoğraf-önce/kayıt-sonra, `rule_snapshot`; `sistem_olayi_yaz` (`CAMERA_DOWN`/`AUDIO_CHANNEL_DOWN` için).
- `veritabani.py` sürümlü şema + `DALSAN-SEMA: YABANCI-ANAHTAR-KAPALI` işareti; `zaman.py`; `loglama.py`; `hatalar.py`; `kaynaklar.py`.
- Web: bölge editörü, rapor (`rapor_verisi` tek kaynak), gölge mod, inceleme kuyruğu, `rtsp_maskele`, `guvenli_json`.
- Test altyapısı: `conftest.istemci`, `sema_bilgisi.py`, `tests/nesne_kiyas` metodolojisi (tespit doğruluk takımına şablon), `tests/hiz_kiyas`.
- `analiz/alan_bulucu.py` + `web/alan_rotalari.py` ("Alanları Otomatik Bul"): **kalır.** §4.2 bu yeteneği v3'e erteliyor (`GOREV-TANIMI-V2.md:86`); kod gereksinimin önünde (8.A). Yalnız sarı → `pedestrian_path`, beyaz → `loading_area` önerir (`alan_bulucu.py:122-124`). v2'de bölge tipleri değişirse (walkway, vehicle_lane, crossing…) değişecek olan yalnız bu eşleme ve §7.2'deki sabit eşiklerdir; ağır iş zaten havuzda (§4.6).
- `nesneler/` (kutuphane, arama, depo, teshis) + `/nesneler`: **dokunulmadan kalır, v2 kapsamı dışında.** Canlı analize bağlı değil (`nesneler/__init__.py:1-8`, `uygulama.py:128-131`). §4.1'in kapalı sınıf listesi tespit modelinin çıktısıdır: sabit kimlikli 7 sınıf (`GOREV-TANIMI-V2.md:58-70`). Kullanıcının fotoğrafla tanıttığı serbest "nesneler" bu listeye girmez. Kütüphaneyi canlıya bağlamak kapalı liste ilkesiyle çelişir, bu yüzden canlıya girmemesi v2 ile uyumludur. v2 ile tek temas noktaları şema (003/004), bakım dışı disk klasörü (R23) ve test süresidir: `test_nesne_kiyas_kapisi` tam paketin ~%44'ü (§5).

### 9.2 Değişmesi gerekenler

- `tespit.py:31-36` sınıf eşlemesi + `tipler.py:35` + `ortak.py:45` + `kural_form.html` sabit checkbox'ları → tek sınıf kataloğu; forklift/loader/pallet_jack/car için ince ayarlı model.
- `takip.py:32` ByteTrack parametreleri (`lost_track_buffer`, activation) `.env`'e.
- `kkd_siniflandirici.py:54-59` gerçek ONNX çıkarımı; `supervizor.py:90` sabiti.
- `supervizor.py` tek iş parçacığı: kalıcılığı kuyruğa, bekçi, işlenen fps/gecikme sayacı.
- `anons.py:AnonsYoneticisi` → kanal listesi + tek işçi + öncelik + periyodik sağlık; `ANONS` tekil seçimi → çoklu kanal.
- `ses_cihazlari.cihaz_bagli_mi` → varsayılan çıkışı da izleyen sağlık (R37); `anons.html` rozeti (R38); ses çıkışı kaydından sonra ayar yenileme (R39); komuta anons ekranına ses çıkışı kartı (R40); fabrika container'ı için ses yolu kararı (R36).
- `Ihlal` (`tipler.py:100-107`) + `events` şeması → durum, `resolved_at`, önem, güven.
- `sema/001` CHECK listeleri (bölge tipleri, olay durumu) → yeni göç.
- `/saglik` → liveness/readiness + düz metin metrik; launcher (`dalsan_launcher.py:266-277`) ve compose healthcheck birlikte.
- Kimlik: şifre alanı, XFF, CSRF, çerez sırrı (R7–R9, R15, R16).
- Paketleme/çalışma zamanı: GPU imajı, Python üst sınırı, lock dosyası.

### 9.3 "Bilerek yapılmadı" denilen ve gereksinimle çelişenler

| Gereksinim | Karar kaynağı | Kararın özü |
|---|---|---|
| Uygulama içi BT eşleştirme | `docs/14:55` (§2.1.1); E2 | "Program eşleştirmeyi kendisi yapmaz" |
| Sunucu TTS (piper/espeak-ng) | docs/14 §8; docs/01:99; E3 | yeni çalışma zamanı; WAV yeterli |
| SIP/ONVIF hoparlör | docs/14 §8; E4 | HTTP tetikleyici yeterli |
| Ses seviyesi | docs/14 §8 | "amfinin işidir" |
| Windows cihaz seçimi | `ses_cihazlari.py:14-32` | PortAudio paketleme riski |
| yaml yapılandırma | CLAUDE.md §7; E5 | `.env` + SQLite |
| Kamera başına süreç | CLAUDE.md:47; docs/09 #1; E6 | TEK program |
| PostgreSQL/Prometheus/MQTT/WebSocket | docs/09; docs/01:94; ADR-005; E7 | en az parça; SSE |
| Olay klibi | ADR-009 (`docs/05:105-108`); docs/08:49 | ham video yok, klip Phase 2 |
| Kalibrasyonsuz piksel mesafesi | docs/03:58-61; docs/08:47 | yaklaşık sonuç üretilmez |
| KKD recall taahhüdü | docs/04:376-378; E10 | yalnız raporlanır |
| KKD dışlama modeli (`ppe_exempt`) | docs/04:44; docs/08 R9 | KKD yalnız çizilen bölgede |
| Roller, denetim günlüğü, 2FA | docs/15 §7 (`:187-188`); docs/01:121,128 | tek kullanıcı varsayımı |

## 10. Dokümanlar ile kod arasındaki çelişkiler

| Doküman iddiası | Doküman | Kod gerçeği | Kod |
|---|---|---|---|
| İki süreç api + analyzer | `docs/02:3-12` | Tek süreç, iş parçacığı | `uygulama.py:81-85` |
| `/api/v1/stream` SSE | `docs/02:103-104` | Uç `/olaylar/akis` | `olaylar_web.py:98` |
| Supervisor yeniden bağlanır | `docs/02:119` | Kamera iş parçacığı yapar | `kamera.py:140-209` |
| GPU hatasında süreç çıkar | `docs/02:120` | Tüm hatalar yutulur, CPU'ya düşülür | `supervizor.py:252-254`; `tespit.py:126-132` |
| KKD batch + piksel eşiği önce | `docs/02:122`; docs/04:44 | Tek tek; eşik rules'ta sonradan | `boru_hatti.py:286-310`; `kkd.py:105-111` |
| Alt akış kullanılır | `docs/02:118` | Seçim yok, `source_url` açılır | `kamera.py:223` |
| ADR-002 "AÇIK" | `docs/05:65-66` | YOLOX fiilen seçilmiş | `requirements.txt:13-14`; `tespit.py:1-5` |
| `sse-starlette` | `docs/05:22` | Kurulu değil; elle StreamingResponse | `requirements.txt`; `olaylar_web.py:138-142` |
| CPU-only ~1-2 fps | `docs/05:52-53` | 4 kamerada kamera başına `tiny` 6,0 fps, `s` 2,4 fps (ölçüm) | AUDIT-OLCUM §1.2 (tablo), §1.3 #1 (yorum) |
| GPU bloğunu aç + cuda | `docker-compose.yml:37` | İmajda yalnız CPU ORT | `requirements.txt:21`; `Dockerfile:18` |
| Üç kural tipi | `docs/09:40` | Dört tip (vehicle_speed) | `motor.py:25`; `sema/005:48-49` |
| Otomatik yeniden başlar | `docs/09:98-99` | Bekçi yok | `supervizor.py:209-221` |
| `EventSink` arayüzü var | `docs/01:138` | Yok (grep boş) | `olaylar/anons.py` |
| `Announcer.play(message_key)` | `docs/02:163` | `cal(anahtar, metin, ses_dosyasi)` | `anons.py:51,125,241` |
| Şifre kapalı | `README.md:53`; `docs/01:120` | Şifre mekanizması var | `giris.py:139-149`; `ayarlar.py:211` |
| Giriş şifresi "⏳ bilerek kapalı (docs/07 #0)" | `README.md:53` | docs/07 aynı maddeyi "**Kapandı**" diye işaretler (doküman ↔ doküman); kodda mekanizma var, varsayılan boş | `docs/07-YOL-HARITASI.md:42`; `.env.example:107`; `ayarlar.py:173`, `:211` |
| "KKD modeli eğitimi ve gölge mod ⏳" | `README.md:55` | Gölge mod mekanizması var; KKD'nin gölge mod ölçümü (`docs/04:382-390`) model olmadığı için koşulamaz. README bu anlamda doğru, §8.C "exists" mekanizmayı sayar | `supervizor.py:555-557`; `kkd_siniflandirici.py:54-59` |
| Komuta anons ekranı ses çıkışı tablosunu göstermeli | `anons_web.py:69-72` (docstring) | `ses_cikisi_baglami` yalnız `/anons`'ta çağrılır; `/komuta/anons` yalnız bağlantı verir | `anons_web.py:62`; `komuta.py:235-240`; `komuta_anons.html:34` |
| "Kontrol Paneli sistemi şu komutla başlatır (değiştirilemez): `uvicorn app.main:app --host 127.0.0.1`" | `main.py:1-3` (docstring) | Paketlenmiş program uvicorn CLI'yi değil, kendi sürecinde `uvicorn.Server`'ı kullanır; host `dinleme_adresi()` | `dalsan_launcher.py:603-620`; `main.py:35-43` |
| Canlı görüntü Phase 2 | `docs/07:21` (#7) | Overlay'li önizleme var | `kameralar.py:319-332` |
| NTP runbook'ta | `docs/08:13` (R7) | docs/06'da NTP yok | `docs/06-OPERASYON.md` |
| systemd `app.main:uygulama` | `docs/06:83` | Sembol `app` | `main.py:63` |
| `egitim/`, `modeller.py` | `CLAUDE.md:91,97` | Dizin/dosya yok | `backend/app/` |
| Şema "geri alınabilir" | `CLAUDE.md:86` | Geri alma yok | `docs/06:185`; `veritabani.py:85-161` |
| Python 3.12 | `CLAUDE.md:42` | `.venv` 3.11.15; launcher ≥3.11 | `.venv/pyvenv.cfg`; `dalsan_launcher.py:209` |
| Python 3.10+ | `docs/11:96` | Eşik 3.11 | `dalsan_launcher.py:209` |
| Bölge rengi mavi | `docs/12:19` | Mor (200,60,160) | `boru_hatti.py:59` |
| `rules/ppe.py` | `docs/03:103` | Dosya `rules/kkd.py`; `rules/ppe.py` yok | `backend/app/rules/kkd.py` (§1 listesi) |
| 7 tablo | `docs/02:80-90` | 11 tablo + `sema_surumu` | `backend/sema/001-006` |
| `.env.example` 29 ayar | `docs/ILERLEME.md:62` | 33 anahtar | `.env.example` |
| "Paketleme yok" | `pyproject.toml:1` | `paketleme/` var | `paketleme/paketleme_ortak.py` |
| "İşlenen kare" gösterilir | `kilavuz.py:71-72` | Okuma hızı | `kamera.py:312-315` |
| Ekranda uyarı bandı çıkar | `komuta_uyari.html:112` | Komuta şablonları uyari.js yüklemez | `ana_sayfa.html:123`; `olaylar.html:88` |
| Kanıt yalnız oturumla | `olaylar_web.py:248-249` | Şifre boşken kimliksiz | `giris.py:146` |
| Kilit betiği durdurur | `docs/15:64-67` | XFF ile atlanır | `giris.py:94-97` |
| Ağa açık+şifresiz oluşamaz | `docs/15:40-42` | Docker `0.0.0.0` sabit | `Dockerfile:40` |
| "docs/AUDIT.md Ek Ö" ölçümleri | `GOREV-TANIMI-V2.md` E12–E14 dipnotu | Ölçümler `docs/AUDIT-OLCUM.md`'de | — |
| Satır atıfları (içerik doğru) | AUDIT-OLCUM §1.3-4: `requirements.txt:14`, `Dockerfile:26`, `tespit.py:163`; §1.3-5: `.env.example:31` | Güncel satırlar `:21`, `:18`, `:159/:175`; `.env.example:36-40` (`:31` `KKD_ORNEK_SAAT_LIMIT`'tir) | — |
| "Tekrar bastırma: `ANONS_BEKLEME_SN=30`, `_son_anonsu_yaz()`" | AUDIT-OLCUM §2.3 | Bastırma `Cooldown` ile yapılır; `_son_anonsu_yaz` yalnız `speaker_zones.last_announced_at` yazar | `anons.py:313-314`; `anons.py:368-387` |
| Kanal sağlığı "üç durumlu, var" | AUDIT-OLCUM §2.3 | Seçim boşken hep True; Mac/Windows'ta seçim yok → kopma algılanmaz | `ses_cihazlari.py:105-106`, `:68-74` (R37) |
| "Anons yolları … 5 sn zaman aşımlı"; "komut enjeksiyonu endişesi dayanaksız" | AUDIT-OLCUM §2.4 | 5 sn yalnız cihaz listeleme; ses kartı çalma 20 sn. `shell=True` yok (grep boş, doğru), ama Windows'ta PowerShell `-Command` metni dosya yolundan kurulur; tırnak ikilenerek korunur ve kodun kendi yorumu bunu "komut enjeksiyonu yüzeyi" diye anar | `ses_cihazlari.py:49`; `anons.py:143`; `anons.py:72-83` |
| "Hiçbir sayı tahmin değildir" | AUDIT-OLCUM başı ve §1 | "A2DP 100–250 ms" ölçülmedi, gereksinim belgesinden gelir; "üç bağımsız koşuda %5 içinde" ve "14 sayfa 200" için ham çıktı yok | `GOREV-TANIMI-V2.md:147`; §11 |
| "Günlük JSON yapısaldır; §4.9 zaten karşılanıyor" | AUDIT-OLCUM §2.1 | Uygulama günlüğü JSON; uvicorn CLI yolunda uvicorn'un kendi satırları düz metin ve `sistem.log` dışı (kod okuması) | `loglama.py:84-101` |

**Son yedi satırın durumu:** bu satırlar Faz 0 çürütme turunda bulunan çelişkilerin kaydıdır ve kayıt için yerinde durur. Hepsi bu raporla aynı commit'te giderildi: AUDIT-OLCUM'daki altı çelişki ve satır kaymaları o belgenin §3 düzeltme kaydında, "docs/AUDIT.md Ek Ö" atfı `GOREV-TANIMI-V2.md` EK A dipnotunda düzeltildi. Düzeltme sırasında bir hata daha çıktı: AUDIT-OLCUM'un "üç koşuda %5 içinde" iddiası yanlıştı, koşular arası fark `yolox_tiny`'de %13,9'dur. Ölçümün asıl sonuçları (bütçe %100 / %40, GPU paketi yok) değişmedi.

## 11. DOĞRULANMADI listesi

1. YOLOX 0.1.1rc0 ONNX'in beklediği girdi düzeni (BGR, 0-255, normalizasyonsuz) — üst kaynakla karşılaştırılmadı (`tespit.py:181-189`).
2. `models/*.onnx` dosyalarının hash'i/bütünlüğü; resmi yayınla eşleşme.
3. Fabrika sunucusunun Python sürümü, GPU modeli, `onnxruntime-gpu` CUDA/cuDNN eşleşmesi.
4. FFmpeg RTSP varsayılan okuma zaman aşımının fiili değeri (R4'ün şiddeti buna bağlı).
5. Gerçek kamerada tespit doğruluğu (person recall, araç mAP) — hiç ölçülmedi.
6. SH17 veri setinin CC BY-NC-SA 4.0 olduğu (E1); CHV, Pictor-PPE, Roboflow forklift lisansları; COCO ağırlıklarının eğitim verisi lisansı.
7. `onnxruntime==1.19.2` için cp313/cp314 tekerleği olmadığı (uyumluluk avcısının PyPI sorgusu; bu raporda tekrarlanmadı) ve python.org varsayılan indirmesinin 3.14 olduğu.
8. `.env` satır enjeksiyonu (R14), `compare_digest` `TypeError` (R15), Docker'da `.env :ro` yüzünden Ayarlar kaydının başarısızlığı (R27) — kod okumasına dayanır, çalıştırılmadı.
9. systemd biriminin `app.main:uygulama` yüzünden başlamadığı (R26) — docs/07 "provası yapıldı" diyor; çalıştırılmadı.
10. Docker imajının derlendiği/çalıştığı (`docs/ILERLEME.md:394` "denenemedi").
11. Kopuk Bluetooth sink'e `paplay --device`'ın sıfır dışı kodla döndüğü; eşzamanlı `aplay`'in "device busy" verdiği; PipeWire'da `pipewire-pulse` varlığı.
12. Windows `Get-PnpDevice -Class AudioEndpoint`'ın mikrofonları da listelediği; PowerShell çıktısının Türkçe cihaz adlarını bozması.
13. Tarayıcı `speechSynthesis` Türkçe sesinin çevrimdışı çalıştığı.
14. Tarayıcıların Private Network Access engelinin R8 CSRF vektörünü kısıtlayıp kısıtlamadığı.
15. FastAPI `/docs` ve `/openapi.json`'ın kimliksiz açık olduğu (varsayılan davranış; çalıştırılmadı).
16. Nesne kütüphanesinin "8/204 isabet" (`kutuphane.py:180`, `docs/07:167`), "~19 ms/fotoğraf" ve docs/07 §5.1 AUC tablosu — "8/204"ün takımı `tests/nesne_kiyas` ama bu raporda koşulmadı; "~19 ms" ve AUC tablosunu hangi kodun ürettiği bulunamadı.
17. Dalsan sahasında loader/pallet_jack bulunup bulunmadığı; gece/ışık koşulları.
18. Rev.02 ek protokolünün imzalandığı (KKD veri toplama bunun şartı, docs/00:63-64); docs/08 §2'deki 10 açık kararın akıbeti.
19. Tam paketin Python 3.12 altında aynı sonucu verdiği (koşu 3.11 venv'inde yapıldı, `by392r477.output:22`); PyInstaller kuruluyken 17 atlanan testin geçtiği.
20. `python:3.12-slim` imajında `tzdata` varlığı (kod sabit UTC+3'e düşer, `zaman.py:16-22`).
21. Windows Kontrol Paneli `terminate` yolunda lifespan kapanışının (kamera iş parçacıklarının durdurulması) çalıştığı.
22. Bloke eden I/O sürelerinin (R11, R22) gerçek büyüklüğü — ölçülmedi.
23. Ayrı `pytest tests/rules -q` → "85 passed in 0.26s" koşusu: çıktı dosyası yok (`tasks/` içinde `85 passed` geçmiyor). 85 testin geçtiği yalnız tam paketten çıkarılır (§5).
24. Push öncesi ikinci tam paket koşusu (1023 geçti, 17 atlandı, ruff temiz): iş akışı bildirimi; ham çıktı, süre ve uyarı sayısı bu rapora ulaşmadı.
25. "A2DP 100–250 ms" ölçülmedi, görev tanımından gelir (`GOREV-TANIMI-V2.md:147`; `docs/16` §4 de DOĞRULANMADI der). *Aynı maddede duran iki eksik giderildi:* 15 adres denemesinin ham çıktısı AUDIT-OLCUM §2.2'ye, üç koşunun ham sayıları §1'e eklendi; "%5 içinde" iddiası yanlıştı ve düzeltildi.
26. Fabrika imajında `aplay`/`paplay`/`pactl` bulunmadığı (R36): imaj derlenmedi; `ffmpeg` apt paketinin bağımlılıklarının `alsa-utils` getirmediği varsayıldı.
27. Ses çıkışı kaydından sonra test sesinin eski çıkışa çaldığı (R39) ve liste okunamadığında yeşil "bağlı" rozeti (R38): kod okuması, çalıştırılmadı.
28. macOS `system_profiler` çıktısındaki `coreaudio_device_transport` alanının Bluetooth için gerçek değeri.
29. uvicorn CLI yolunda uvicorn'un kendi günlük satırlarının düz metin olduğu ve `sistem.log`'a girmediği (§4.4): kod okuması.
30. §7.3 bellek taraması kod okumasına dayanır; uzun süreli bellek ölçümü yapılmadı.
31. `(1,3549,85)` ham çıktı şeklinin gözlendiği çıkarım koşusu (kaydı yok; aritmetikle tutarlı, §3); `tests/nesne_kiyas`'taki 264 − 204 = 60 sorgunun negatif olduğu.
32. 17 atlamanın dosyalara dağılımı (mac 5, paketleme 12): çıktı satırlarının alfabetik toplama sırasıyla eşlenmesinden çıkarıldı.

## 12. Doğrulama izi

Bu rapor yazıldıktan sonra iki denetimden geçti: iddiaların tek tek çürütülmeye çalışıldığı
bir tur ("kod gerçeği" ve "atıf doğruluğu" merceği) ve bir eksiklik eleştirmeni.

| Adım | Sayı | Ayrıntı |
|---|---|---|
| Üretilen iddia | 64 | C01–C64 (§1–§10'dan çıkarılan, kanıt atıflı cümleler) |
| Çürütme alan | 4 | C03, C14, C28, C29 |
| Çürütmesi haklı bulunup düzeltilen | 4 | **C03** (§1): "tek giriş noktası modül düzeyi `app`" yanlış; CLI yolu ve paketlenmiş programın `uygulamayi_kur()` yolu ayrıldı, çift çağrı notu eklendi. **C14** (§3, R17, §7.2): `model_indir.py:21` atfı iddiayı desteklemiyordu; doğru atıflar `:79-85`, `:22`, `:69` ve `models/indir.sh:10-15`, "1 MB" → "1 MiB". **C28** (§5): sayılar `:45`'te, ruff `:3-4`'te, çıkış kodu `:46`'da; koşunun Python 3.11'de yapıldığı eklendi. **C29** (§5, §10): 85'in dosya dağılımı eklendi; `test_kkd.py:68` sayımın değil "belirsiz olay üretmez" testinin atfıdır; ayrı `tests/rules` koşusu kaydı olmadığı için DOĞRULANMADI'ya taşındı |
| Çürütmesi reddedilen | 0 | — |
| Çürütme almayan | 60 | Olduğu gibi kaldı. Değişen satır atıfları (ör. C30'un `pytest.skip` yeri, `test_paketleme.py:97-98`) kendi bölümünde düzeltildi |
| DOĞRULANMADI'ya taşınan (iddia düzeyinde) | 1 alt iddia | C29'un "`pytest tests/rules -q` → 85 passed in 0.26s" kısmı (§11 #23). Tam iddia taşınmadı |
| Eleştirmen maddeleri | 29 | 15 eksik + 14 zayıf; hepsi işlendi: bellek adayları §7.3; eksik dosyalar §1; komut çıktıları §6; Bluetooth/ses §4.2 (container, kör nokta, komuta ekranı, bayat ayar, platform tablosu, testler) ve R36–R41; README ⏳ ve şifre §8.C, §8.F, §10; R22 genişletildi; indeks ve ON DELETE §4.5; arayüz adı §3; video yükleme §2; kaynaksız sayılar §3, §4.2, §6, §7.1 R6, §7.2, §8.A, §8.B |
| §11'e eklenen yeni madde | 10 | #23–#32 (toplam 32 madde) |
| AUDIT-OLCUM ile çelişki | 7 | §10'un son satırları. Önceden bilinen 1: satır kaymaları (`requirements.txt:14`, `Dockerfile:26`, `tespit.py:163`). Bu turda bulunan 6: satır atfı `.env.example:31`; `_son_anonsu_yaz` bastırma değil; kanal sağlığı kör noktası; zaman aşımı ve PowerShell komut metni; "hiçbir sayı tahmin değildir" (A2DP ve kaydı olmayan iki cümle); uvicorn günlük biçimi. GPU, fps bütçesi ve sağlık ucu sayılarında çelişki yok. Düzeltici AUDIT-OLCUM'u değiştirmedi; yedisi de sonradan, aynı commit'te AUDIT-OLCUM §3'te düzeltildi |

Test sonucu kaynağı: `tasks/by392r477.output` (1. koşu, ham) ve iş akışı bildirimi (2. koşu, ham
çıktısız). Donanım çıktıları bu turda alındı (§6).
