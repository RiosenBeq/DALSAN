<!-- Bu dosya, v2 (saha güvenliği genişletmesi) çalışmasının GÖREV TANIMIDIR.
     Operatörün 22 Eyl 2026'da verdiği isteğin düzeltilmiş ve ölçülmüş hâli.
     Tasarım kararı DEĞİLDİR: kararlar docs/17-V2-TASARIM.md'de toplanır.
     Çelişki hâlinde docs/09-BASITLESTIRME-KARARLARI.md ve CLAUDE.md üstündür. -->

# GÖREV TANIMI: Dalsan Saha Güvenliği Görsel Algılama Sistemi

## 0. Rol ve çalışma disiplini

Sen endüstriyel bilgisayarlı görü, gerçek zamanlı video analitiği ve iş sağlığı ve güvenliği (İSG) sistemleri konusunda kıdemli bir mühendissin. Bu projede kodu sen yazacaksın; sıralama şudur: ÖNCE ANLA, SONRA TASARLA, SONRA YAZ, SONRA ÖLÇ.

Kurallar:
1. Faz 0 (keşif) bitmeden hiçbir dosyayı değiştirme.
2. Doğrulamadan iddia etme. Kütüphane sürümü, lisans, donanım kapasitesi, model doğruluğu: kaynağından doğrula. Doğrulayamadığını "DOĞRULANMADI" etiketiyle yaz.
3. Ölçmediğin metriği yazma. "Çalışması lazım" bir sonuç değildir; komut ve çıktıyla kanıtla.
4. Yalnızca §8'deki sorularda dur. Diğer belirsizliklerde varsayımını açıkça yaz ve devam et.
5. Mevcut hiçbir özelliği bozma. Her faz sonunda tüm testler geçmeli.
6. Kullanıcıya görünen her metin (sesli uyarı, arayüz, rapor) Türkçe; kod, tanımlayıcı, dosya adı, commit mesajı İngilizce.
7. Kapsamı sessizce daraltma. Yapamadığın bir şey varsa yapamadığını ve nedenini yaz.

## 1. Bağlam (operatör doldurur; boşsa Faz 0'da kod tabanından çıkar)

| Alan | Değer |
|---|---|
| Depo / dizin | `RiosenBeq/DALSAN` (branch `main`); tek program: `backend/app/main.py` (FastAPI + arka plan analiz iş parçacığı) |
| Uç cihaz / sunucu | Fabrika: Linux + Docker, **NVIDIA ≥ 8 GB GPU, ≥ 6 çekirdek, ≥ 16 GB RAM, ≥ 512 GB SSD** (docs/05 §3). Geliştirme: Mac/Windows, Kontrol Paneli (`masaustu/dalsan_launcher.py`) |
| İşletim sistemi | Fabrika: Ubuntu + Docker (tek container, `docker-compose.yml`). Geliştirme: macOS / Windows 11 |
| Kameralar | **3–4 mevcut RTSP kamera** (docs/00 kapsam takası; Rev.01'deki 8–10'dan düşürüldü); kamera başına örnekleme `KARE_ORNEKLEME_FPS=6`; video dosyası kaynak tipi de var |
| Mevcut model / çerçeve | **YOLOX** (Apache-2.0, ADR-002) `yolox_tiny.onnx` (geliştirme) / `yolox_s.onnx` (fabrika), **ONNX Runtime 1.19.2 CPU paketi** (`CIKARIM_CIHAZI=cuda` seçeneği var ama `onnxruntime-gpu` depoda hiçbir yerde kurulmuyor — **ölçüldü**, bkz. E12), supervision 0.25.1 ByteTrack; forklift ayrı sınıf DEĞİL (COCO araç sınıfları); KKD sınıflandırıcı henüz eğitilmedi |
| Bluetooth hoparlör | Bugün: yalnız **işletim sistemi eşleştirmesi** + Anons sayfasından ses çıkışı seçimi (Linux'ta `ANONS_SES_CIHAZI`); docs/14 §2.1.1 uygulama içi eşleştirmeyi **bilerek yapmamış** ("OS'un işini ikinci kez, daha kötü yapmak"). Cihaz modeli, adedi, mesafe: **operatör dolduracak** |
| Saha koşulları | Alçı fabrikası (DALSAN Alçı, docs/00): toz, iç/dış mekân karışık, metal raf ve duvar (Bluetooth menzili için docs/14 uyarısı); gece/ışık koşulu: **operatör dolduracak** |
| Alarm alıcıları | Bugün: ekran bandı + ses (ses kartı / HTTP IP hoparlör) + olay kaydı; kişiler: **operatör dolduracak** (İSG uzmanı? vardiya şefi?) |

## 2. Orijinal istek ve düzeltilmiş yorumu

Orijinal: "Dalsan projesini tamamıyla incele; forklift, tır, yaya yolu vb. nesneleri ve insanı tanı; baretsiz ve yeleksizleri anla; Bluetooth ile hoparlöre bağlanma seçeneği ekle."

Bu istek şöyle yorumlanacak:
- "Nesneleri tanı" = kapalı sınıf listesiyle nesne ALGILAMA (§4.1). "vb." yoktur; liste kapalıdır.
- "Yaya yolu" bir nesne değil, kamera başına tanımlanan bir BÖLGEDİR (§4.2).
- "Baretsiz / yeleksiz" = insan bazlı KKD uyum denetimi; üç durumlu: var / yok / belirsiz (§4.3).
- "Hoparlöre bağlanma seçeneği" = çok kanallı uyarı altyapısının bir kanalı; tek başına güvenlik kanalı olamaz (§4.6).

## 3. Faz 0: Keşif ve denetim (kod değiştirmeden)

Çıktı: `docs/AUDIT.md`. İçermesi gerekenler:
1. Depo haritası: dizinler, giriş noktaları, çalışma zamanı (Python sürümü, CUDA, paket listesi ve sürümleri).
2. Mevcut video hattı: kaynak (RTSP/USB/dosya), çözme, ön işleme, model, son işleme, çıktı. Hangi dosyada, hangi fonksiyonda.
3. Mevcut model(ler): mimari, ağırlık dosyası, eğitim verisi, sınıf listesi, lisans, ölçülmüş metrik var mı.
4. Mevcut uyarı mekanizması, kayıt, arayüz, yapılandırma biçimi.
5. Testler: var mı, çalışıyor mu (çalıştır ve çıktıyı yapıştır).
6. Donanım keşfi: `nvidia-smi`, `lscpu`, `free -h`, `bluetoothctl --version`, `aplay -l` çıktıları (mevcutsa).
7. Teknik borç ve riskler: sabit kodlanmış eşikler, sırlar, bloke eden I/O, bellek sızıntısı adayları, kırık bağımlılıklar.
8. Yeni gereksinimlerle (§4) çakışan ya da yeniden kullanılabilecek parçalar.

## 4. Hedef sistem gereksinimleri

### 4.1 Nesne sınıfları (kapalı liste, `config/classes.yaml`)

| id | sınıf | Türkçe | Not |
|---|---|---|---|
| 0 | `person` | insan | Her KKD kuralının öznesi |
| 1 | `forklift` | forklift | COCO'da yok; özel veri gerekir |
| 2 | `truck` | tır / kamyon | Çekici + dorse tek kutu |
| 3 | `loader` | yükleyici / kepçe | Dalsan sahasında varsa (Faz 0'da doğrula) |
| 4 | `pallet_jack` | transpalet | Manuel ve elektrikli |
| 5 | `car` | binek / pikap | |
| 6 | `pallet` | palet | v2, isteğe bağlı |

Sınıf kimlikleri sabittir; yeni sınıf listeye eklenir, eski kimlik değişmez.

### 4.2 Bölgeler (zone): nesne değil, yapılandırma

| tür | Türkçe |
|---|---|
| `walkway` | yaya yolu |
| `vehicle_lane` | araç yolu |
| `crossing` | yaya-araç geçidi |
| `loading_dock` | yükleme rampası |
| `restricted` | yasak alan |
| `ppe_exempt` | KKD muaf alan (ofis, kabin, dinlenme) |

- Kamera başına `config/zones/<camera_id>.yaml`; koordinatlar 0..1 normalize; çokgen.
- Arayüzde çizilebilir ve düzenlenebilir (§4.11).
- Bölge testi, kutunun MERKEZİYLE değil AYAK NOKTASIYLA (alt-orta) yapılır.
- Boyalı çizgilerden otomatik bölge önerisi (segmentasyon) v3'e ertelenir; v1'de manuel.

### 4.3 KKD (baret ve yelek) uyumu

- Önce `person` algılanır, sonra her insan için `helmet` ve `vest` durumu belirlenir: `present | absent | unknown`.
- Yöntem seçimi Faz 1'de gerekçelendirilir: (a) iki aşamalı (insan kırpıntısı → baş/gövde sınıflandırıcı) ya da (b) tek aşamalı (`helmet`, `no_helmet`, `vest`, `no_vest` sınıfları IoU ile insana bağlanır).
- `unknown` koşulları: baş/gövde görünmüyor, kutu kare kenarında kesik, kutu yüksekliği `min_person_px` altında (varsayılan 60 px), bulanıklık eşiği aşıldı.
- `unknown` ASLA ihlale dönüşmez.
- Araç kabinindeki kişi (forklift sürücüsü) ayrı ele alınır: `ppe_rules.driver_helmet_required` yapılandırmasıyla.
- Bilinen zor örnekler ve zorunlu negatif veri: beyaz saç / beyaz şapka vs beyaz baret; yansıtıcı ceket vs yelek; gece ışığında yansıma; sırt çantası; yağmurluk.

### 4.4 Takip (tracking)

- ByteTrack ya da BoT-SORT; her nesneye kararlı `track_id`.
- İhlaller kare bazında değil, iz (track) bazında ve zaman penceresinde değerlendirilir.
- Yeniden tanıma (Re-ID) v1 dışı.

### 4.5 Kural motoru ve olaylar

Bütün eşikler `config/rules.yaml` içinde; kodda sabit sayı yok. Her kural: `min_duration_s`, `min_ratio`, `cooldown_s`, `severity`, `zones`.

| olay | koşul (varsayılan) | önem |
|---|---|---|
| `PPE_NO_HELMET` | İz üzerinde son 2 s'de karelerin ≥ %70'inde `helmet=absent`, `ppe_exempt` dışında | HIGH |
| `PPE_NO_VEST` | Aynı mantık, `vest=absent` | MEDIUM |
| `PERSON_IN_VEHICLE_LANE` | Ayak noktası `vehicle_lane` içinde ≥ 1.5 s | MEDIUM; aynı bölgede araç varsa HIGH |
| `VEHICLE_ON_WALKWAY` | Araç ayak noktası `walkway` içinde ≥ 1 s | HIGH |
| `VEHICLE_PERSON_PROXIMITY` | Hareketli araç ile insan arası mesafe `proximity_m` altında (varsayılan 3 m) | CRITICAL |
| `RESTRICTED_ENTRY` | İnsan `restricted` içinde ≥ 1 s | HIGH |
| `CAMERA_DOWN` | Kameradan 10 s'den uzun süre kare yok | sistem |
| `AUDIO_CHANNEL_DOWN` | Ses kanalı 30 s'den uzun süre sağlıksız | sistem |

- Mesafe için kamera başına homografi kalibrasyonu (`config/calibration/<camera_id>.yaml`, zemin düzlemi). Kalibrasyon yoksa piksel tabanlı sezgisel yöntem kullanılır, olay `confidence: low` ile işaretlenir ve metre iddia edilmez.
- Olaylar durum makinesidir: `ACTIVE → RESOLVED`; aynı iz için `cooldown_s` içinde tekrar üretilmez; histerezis (giriş eşiği ≠ çıkış eşiği).
- Her olay: `event_id, camera_id, track_id, type, severity, confidence, zone, started_at, resolved_at, snapshot_path, clip_path`.

### 4.6 Uyarı kanalları ve Bluetooth hoparlör

Ortak arayüz: `AlertChannel { send(event), health(), name }`. Dağıtıcı (`AlertDispatcher`):
- Öncelik kuyruğu: CRITICAL her şeyi keser; aynı anda tek ses çalar.
- Hız sınırı: kanal başına dakikada en fazla `N` sesli uyarı; aynı olay `cooldown_s` içinde tekrar çalınmaz; aynı türden eş zamanlı olaylar birleştirilir ("2 kişi baretsiz").
- Türkçe sesli uyarı: öncelik önceden kaydedilmiş WAV (`assets/audio/tr/*.wav`); dinamik metin için çevrimdışı TTS (piper Türkçe ses varsa; yoksa espeak-ng; internet gerektiren TTS yalnız isteğe bağlı).
- Bir güvenlik olayı EN AZ BİR sağlıklı kanala ulaşmalı; hiçbiri sağlıklı değilse panel + günlük CRITICAL kaydı.

Kanallar:

| kanal | durum |
|---|---|
| `local_audio` (kablolu: ALSA / PulseAudio / PipeWire) | v1, varsayılan |
| `bluetooth_audio` | v1, isteğe bağlı |
| `dashboard` (canlı bildirim) | v1 |
| `webhook` (HTTP POST, imzalı) | v1 |
| `ip_speaker` (SIP / ONVIF) | v2 |
| `messaging` (Telegram / e-posta / SMS) | v2 |
| `stack_light` (GPIO / Modbus) | v2 |

`bluetooth_audio` şartnamesi:
- Linux'ta BlueZ üzerinden D-Bus (`org.bluez`), A2DP sink profili. Windows hedefleniyorsa sistem ses aygıtı seçimi (WASAPI) ile eşleştirilmiş cihaz; hangisi olduğu Faz 0'da belirlenir.
- Arayüzde: tara → eşleştir → güven → bağlan; MAC adresi `config/alerts.yaml` içinde saklanır.
- Otomatik yeniden bağlanma (üstel geri çekilme, üst sınır 60 s); her 10 s sağlık kontrolü; 30 s'den uzun kopuksa `local_audio`'ya düş ve `AUDIO_CHANNEL_DOWN` üret.
- Ses seviyesi ayarı ve "test sesi çal" düğmesi.
- Gecikme ölçülür ve raporlanır (A2DP tipik olarak 100–250 ms; kabul: uçtan uca bütçe içinde kalması).
- Belgelenecek sınırlar: menzil ~10 m, metal yapı ve motor gürültüsü etkisi; birden fazla hoparlör gerekiyorsa bölge başına bir cihaz.
- Bluetooth TEK uyarı kanalı olamaz.

### 4.7 Veri ve model

- Önce mevcut veri ve modeli değerlendir (Faz 0). Yoksa: COCO ön-eğitimli `person`, `truck`, `car` + özel `forklift`, `loader`, `pallet_jack` + KKD.
- Aday açık veri setleri (KULLANMADAN ÖNCE lisans ve uygunluk doğrula): KKD için SH17, CHV, Pictor-PPE; forklift için Roboflow Universe setleri.
- Saha verisi: Dalsan kameralarından KVKK dayanağı belgelenmiş görüntü; etiketleme kılavuzu `docs/ANNOTATION.md` (kutu kuralları, kesik nesne, örtüşme, baret vs şapka, yelek vs yansıtıcı ceket, kabin içi sürücü).
- Ayrım: kamera ve gün bazında (aynı çekimden kare hem eğitim hem testte olamaz).
- Artırma: toz/sis, düşük ışık, hareket bulanıklığı, yağmur, parlama, ölçek.
- Model adayları: Ultralytics YOLOv8 / YOLO11 (AGPL-3.0: ticari kullanımda lisans gerekir, operatöre bildir), RT-DETR (PaddleDetection sürümü Apache-2.0, Ultralytics sürümü AGPL), YOLOX (Apache-2.0). Seçimi lisans + donanım + ölçülen doğrulukla gerekçelendir.
- Dışa aktarım: ONNX → TensorRT / OpenVINO; uç cihazda INT8 kalibrasyonlu.
- Model kayıt defteri: `models/<name>/<version>/` + model kartı (veri, metrik, tarih, sha256).

### 4.8 Performans ve kabul kriterleri (hedef; ölçülür, uydurulmaz)

| ölçüt | hedef |
|---|---|
| `person` recall @IoU 0.5 | ≥ 0.95 |
| `forklift`, `truck` mAP50 | ≥ 0.90 |
| `PPE_NO_HELMET` precision / recall | ≥ 0.90 / ≥ 0.85 |
| `PPE_NO_VEST` precision / recall | ≥ 0.90 / ≥ 0.85 |
| Uçtan uca gecikme (kare → ses) | ≤ 500 ms uçta, ≤ 1 s sunucuda |
| Kamera başına işleme hızı | ≥ 10 fps, tüm kameralar eş zamanlı |
| Yanlış alarm | ≤ 2 / saat / kamera |
| Çalışma süresi | ≥ %99.5 / ay |

Hedef tutmuyorsa: gerçek sayıyı yaz, nedenini analiz et, sonraki adımı öner.

### 4.9 Güvenilirlik ve operasyon

- Kamera başına ayrı işçi süreci; gözetmen (supervisor) ve bekçi (watchdog); çökünce otomatik yeniden başlatma.
- Geri basınç: geciken kareler DÜŞÜRÜLÜR, kuyrukta biriktirilmez.
- RTSP kopunca üstel geri çekilmeyle yeniden bağlanma.
- `/healthz` ucu, Prometheus metrikleri (fps, gecikme, kuyruk, kanal sağlığı), JSON yapısal günlük.
- Olay deposu (SQLite v1 / PostgreSQL v2) + olay klibi (öncesi 5 s, sonrası 5 s); saklama süresi yapılandırılabilir (varsayılan 30 gün); disk doluluk koruması.
- NTP zaman eşitleme; yapılandırma sıcak yükleme; düzgün kapanış; `systemd` ile açılışta başlama; Docker imajı.

### 4.10 KVKK, gizlilik, güvenlik

- Çalışanların görüntüsü kişisel veridir: hukuki dayanak, aydınlatma metni ve saha tabelası `docs/KVKK.md` içinde; sorumlu kişi §8'de sorulur.
- Yüz tanıma ve biyometrik kimliklendirme YAPILMAZ.
- Saklanan klip ve dışa aktarımlarda isteğe bağlı yüz bulanıklaştırma (`privacy.blur_faces`).
- Panelde rol tabanlı erişim; kimin hangi klibi izlediği denetim günlüğünde.
- Sırlar (RTSP şifresi, webhook anahtarı) yalnız ortam değişkeninde; günlüklere yazılmaz.
- Varsayılan olarak buluta veri gitmez; ağ bölümlendirmesi belgelenir.

### 4.11 Arayüz ve entegrasyon

- Web paneli (Türkçe): canlı görüntü + kutu/bölge katmanı; bölge editörü; olay listesi + klip; kamera sağlığı; KKD uyum istatistikleri (vardiya / gün / hafta); uyarı kanalı ayarları (Bluetooth eşleştirme sayfası dahil); rapor dışa aktarma (CSV / PDF); kullanıcı yönetimi.
- REST + WebSocket API; giden webhook; isteğe bağlı MQTT.

## 5. Fazlar ve teslimatlar

| faz | kapsam | teslimat | kontrol noktası |
|---|---|---|---|
| 0 | Keşif | `docs/AUDIT.md` | Rapor sun |
| 1 | Tasarım | `docs/ARCHITECTURE.md`, `config/*.yaml` şemaları, olay sözlüğü, §8 soruları | DUR, onay bekle |
| 2 | Çekirdek hat | alma → algılama → takip → bölge → kural motoru → olay deposu; kayıtlı video ile testler | Testler yeşil |
| 3 | KKD | baret/yelek + `unknown` mantığı + değerlendirme raporu | Metrik tablosu |
| 4 | Uyarılar | kanal soyutlaması, kablolu ses, Bluetooth yöneticisi, Türkçe ses varlıkları, panel ayarları | Sahada ses testi |
| 5 | Sertleştirme | performans, güvenilirlik, KVKK, belgeler, dağıtım (Docker / systemd), saha kabul testi | Kabul listesi |

Faz 1 onayından sonra Faz 2–5'i kendi başına ilerlet; yalnız §8 sorularında dur. Her faz kendi commit'lerine ayrılır; küçük ve tanımlı commit'ler.

## 6. Test stratejisi

- Birim: çokgen içi nokta testi, normalize koordinat dönüşümü, kural durum makinesi (sentetik izler), histerezis ve cooldown, uyarı kuyruğu önceliği, Bluetooth yöneticisi (sahte D-Bus ile).
- Entegrasyon: `tests/fixtures/videos/` altında kayıtlı klipler + beklenen olay JSON'u; toleranslı zaman karşılaştırması. Her yanlış alarm bir regresyon vakası olarak eklenir.
- Performans: `scripts/benchmark.py` ile donanım başına fps / gecikme raporu.
- Saha: `docs/RUNBOOK.md` içinde kabul kontrol listesi (kamera açısı, bölge doğrulama, ses duyulabilirliği, yanlış alarm gözlemi).

## 7. Yasaklar

- Ölçülmemiş metrik, "muhtemelen çalışır" ifadesi.
- Kodda sabit eşik ya da sabit sınıf listesi.
- Bluetooth'un tek uyarı kanalı olması.
- `unknown` KKD durumunun ihlal sayılması.
- Yüz tanıma / biyometrik kimliklendirme.
- Depoya sır gömmek.
- Lisansı doğrulanmamış ağırlık ya da veri seti kullanmak.
- Mevcut özellikleri bozmak ya da kapsamı sessizce daraltmak.
- Test atlamak, testi devre dışı bırakarak yeşile çekmek.

## 8. Açık sorular (bunlar için dur)

1. Uç cihaz ve işletim sistemi nedir? (§1 boşsa)
2. AGPL-3.0 lisanslı model kabul edilebilir mi, yoksa ticari lisans ya da Apache/MIT model mi gerekli?
3. Hangi alanlar KKD'den muaf (ofis, kabin, dinlenme)? Forklift sürücüsüne baret zorunlu mu?
4. Sesli uyarının yanında hangi kanallar isteniyor ve kim alacak?
5. Görüntü saklama süresi ve KVKK sorumlusu kim?
6. Kamera sayısı, yerleşimi ve gece koşulu.
7. Mesafe kuralı için zemin kalibrasyonu yapılabilir mi (sahada ölçüm gerekir)?

## 9. Raporlama biçimi (her faz sonunda)

1. Yapılanlar (dosya ve fonksiyon adıyla).
2. Doğrulananlar (çalıştırılan komut + çıktı).
3. Yapılmayanlar ve nedeni.
4. Ölçülen metrikler (tablo).
5. Açık riskler.
6. Sonraki adım.

---

## EK A. Errata — 22 Eyl 2026, depo incelendikten sonra bulunan prompt hataları

Bu prompt DALSAN deposu okunmadan yazıldı. Depo okununca şu maddelerin yanlış ya da çelişkili olduğu görüldü; Faz 1 tasarımı bunları çözmek zorunda:

| # | Prompttaki ifade | Depodaki gerçek / kaynak | Sonuç |
|---|---|---|---|
| E1 | §4.7 SH17 aday veri seti | SH17 lisansı **CC BY-NC-SA 4.0** (ticari kullanıma kapalı); DALSAN ticari müşteri | SH17 elenir; yalnız CC BY / MIT / Apache / CC0 setler |
| E2 | §4.6 uygulama içi Bluetooth tara→eşleştir→bağlan | docs/14 §2.1.1: eşleştirme bilerek işletim sistemine bırakıldı; uygulama yalnız ses çıkışını seçer ve kopmayı Anons sayfasında gösterir | Operatör kararı: bilinçli "yapılmadı" kararı geri mi alınıyor? (§8'e eklendi) |
| E3 | §4.6 piper / espeak-ng TTS | docs/14 §8: sunucuda metinden konuşma **bilerek yapılmadı** (yeni çalışma zamanı); önceden kaydedilmiş WAV tercih edilmiş | Varsayılan WAV kalır; TTS yalnız operatör isterse |
| E4 | §4.6 `ip_speaker` (SIP/ONVIF) v2 | docs/14 §8: SIP bilerek yapılmadı; HTTP tetikleyici yeterli | SIP kapsam dışı |
| E5 | §4.1/4.2/4.5 `config/classes.yaml`, `config/zones/*.yaml`, `config/rules.yaml` | CLAUDE.md §7: eşik/yol `.env` veya veritabanındaki kural parametresi; bölgeler zaten SQLite'ta, arayüzden çizilir | Yaml dosyası yeni "parça"dır; ayarlar `.env` + SQLite tablo olarak kalır |
| E6 | §4.9 kamera başına ayrı işçi süreci | CLAUDE.md §4: **TEK program**, analiz FastAPI içinde iş parçacığı; docs/09 gerekçeli | İş parçacığı modeli korunur; izole hata sınırı + bekçi eklenir |
| E7 | §4.9 PostgreSQL v2, Prometheus, MQTT; §4.11 WebSocket | docs/09: SQLite kararı; CLAUDE.md §3 en az parça; mevcut canlı akış SSE | Yeni servis/kütüphane yok; metrik düz metin, canlı akış SSE |
| E8 | §5 `docs/ARCHITECTURE.md`, `docs/AUDIT.md` adları | Depo dokümanları numaralı ve Türkçe (`00-…15-…`) | `docs/AUDIT.md` (Faz 0), `docs/16-DIS-KAYNAK-DOGRULAMA.md`, `docs/17-V2-TASARIM.md` |
| E9 | §4.7 "veri yoksa COCO ön-eğitimli + özel sınıflar" | docs/04 KKD planı zaten var (iki aşamalı, piksel boyu kısıtı, veri hedefi, politika soruları); KKD teklif Rev.01 kapsamı DIŞI, Rev.02 ek protokol gerekli (docs/00) | Veri toplama ek protokol imzalanmadan başlamaz |
| E10 | §4.8 hedef metrikler | docs/00: "kaçırılan ihlal bilinen sınır, yanlış alarm ciddi kusur"; docs/05: CPU-only KKD için yetersiz, GPU şart | Yanlış alarm hedefi önce gelir; recall hedefleri GPU'ya koşullu |
| E11 | §1 tablo boştu | Yukarıda depodan dolduruldu; kalan üç alan operatörün | — |
| E12 | §1'de "GPU seçeneği var" varsayımı | **Ölçüldü 22 Eyl:** `onnxruntime==1.19.2` CPU paketidir; `get_available_providers()` → `['AzureExecutionProvider','CPUExecutionProvider']`. `onnxruntime-gpu` ne `requirements.txt`'te ne `Dockerfile`'da kurulu. `docker-compose.yml:37` GPU bloğunu açmayı söylüyor ama imaj GPU'yu kullanamaz | Faz 2 öncesi GPU imajı ayrı kurulmalı; kod düşüşü zaten yakalayıp uyarıyor (`tespit.py:124-132`) |
| E13 | §4.8 "≤ 500 ms kare→ses" hedefi | **Ölçüldü:** 4 çekirdek CPU'da 4 kamera yüküyle tespit p90'ı tek başına `yolox_tiny` 121-138 ms, `yolox_s` 473-496 ms | `s` + CPU + Bluetooth birleşimi hedefi karşılayamaz; hedef donanıma koşullu yazılmalı |
| E14 | §4.8 "kamera başına ≥ 10 fps" | docs/05 bütçesi 4 kamera × **6 fps**; ölçüm `tiny` ile tam %100, `s` ile %40 | Hedef 10 fps değil 6 fps olmalı (projenin kendi bütçesi) |

E12–E14 orkestratörün kendi ölçümlerinden gelir (`docs/AUDIT-OLCUM.md`). Faz 0 tamamlandı (`docs/AUDIT.md`); dış kaynak doğrulaması (`docs/16-DIS-KAYNAK-DOGRULAMA.md`) E1'in kapsamını genişletir: §4.7'de adı geçen üç KKD veri setinin **üçü de** ticari kurulumda kullanılamaz (SH17 CC BY-NC-SA 4.0; CHV ve Pictor-PPE lisanssız). §4.6'daki A2DP "100–250 ms" aralığı da orada DOĞRULANMADI olarak işaretlenmiştir; bir ölçüm değildir.
