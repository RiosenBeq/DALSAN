# 17 — V2 Tasarım (Faz 1)

> **Durum:** TASLAK. Operatör onayı bekliyor. **Depo:** `390adf5` (22 Eyl 2026). Bu belgedeki
> bütün `dosya:satır` atıfları bu sürüme göredir ve yazılırken koddan tek tek okundu.
> Üç mercekli inceleme turunun (CLAUDE.md uyumu, kod tabanında uygulanabilirlik, gereksinim
> kapsamı ve güvenlik mantığı) bulguları işlendi; kabul ve ret kaydı §17'dedir.
> **Etiketler:** "DOĞRULANMADI" = kaynağında ya da koddan teyit edilemedi, olgu olarak
> kullanılmaz. "ölçülecek" = sayı yok, ölçüm yöntemi yazılı. "öneri" = başlangıç değeri,
> ölçümle değişebilir.

## 0. Bu belge ne (tarih 2026-09-22; Faz 0 raporu docs/AUDIT.md ve docs/16-DIS-KAYNAK-DOGRULAMA.md'ye dayanır; Faz 2'ye geçmeden operatör onayı gerekir)

**Ne:** `GOREV-TANIMI-V2.md` §5'teki Faz 1 teslimatı. §5 bunun adını `docs/ARCHITECTURE.md`
koyuyordu; E8 gereği numaralı Türkçe düzende bu dosyadır. Kod yazılmadı. Yalnız kısa SQL,
ayar ve arayüz imzası taslakları var.

**Dayanak:** `docs/AUDIT.md` (Faz 0 okuma yarısı), `docs/AUDIT-OLCUM.md` (ölçülen yarı),
`docs/16-DIS-KAYNAK-DOGRULAMA.md` (lisans, TTS, BlueZ, ORT), `GOREV-TANIMI-V2.md` (§4 hedef,
§5 fazlar, §8 sorular, EK A errata E1–E14). Çelişkide sıra şudur: `CLAUDE.md` ve
`docs/09-BASITLESTIRME-KARARLARI.md` > errata (EK A) > §4 metni.

**Nasıl üretildi:** Aynı girdilerden üç tasarım önerisi yazıldı: **EVRİM** (en az parça,
mevcut dosyaların içinde en küçük değişiklik), **ŞARTNAME** (§4'ün her maddesini karşılamak)
ve **GÜVENLİK-ÖNCE** (fail-safe ve yanlış alarm disiplini). Üç ayrı jüri (operatör gözü,
kıdemli mühendis gözü, İSG/KVKK gözü) bunları puanladı:

| Öneri | Operatör jürisi | Mühendis jürisi | İSG-KVKK jürisi | Toplam |
|---|---|---|---|---|
| EVRİM | **21** (birinci) | **20** (birinci) | 20 | 61 |
| GÜVENLİK-ÖNCE | 18 | 19 | **21** (birinci) | 58 |
| ŞARTNAME | 15 | 15 | 13 | 43 |

Bu belgenin iskeleti **EVRİM**dir. Jürilerin "aşılansın" dediği fikirler eklendi; en
önemlileri:

| Aşı | Kaynağı | Bu belgede |
|---|---|---|
| Olay kaydı başarısız olsa da uyarı gider (bugün gitmiyor) | GÜVENLİK-ÖNCE | §3.5 |
| Komuta ekranlarına canlı uyarı bandı + sistem şeridi Faz 2'de | GÜVENLİK-ÖNCE | §11, §13 |
| `analysis_hours` (yanlış alarm/saat paydası), `ANALYSIS_DEGRADED`, CAMERA_UP ve kanal UP için histerezis | GÜVENLİK-ÖNCE | §6, §8, §14 |
| KKD veri toplama kapısı (düzeltme turunda `.env`'den SQLite'a taşındı), örnek piksel sınırı, kalibrasyon kontrol ölçümü (S7'ye koşullu), göç öncesi otomatik yedek | GÜVENLİK-ÖNCE | §5.8, §6.4, §8.4 |
| Durum makinesi cooldown'u değerlendiricilerde bırakır, `degerlendir()` çıktısı değişmez (85 kural testi korunur) | ŞARTNAME | §6.3 |
| `/docs`, `/redoc`, `/openapi.json` kapatılır | ŞARTNAME | §10.5 |
| Dağıtıcı sınırları operatör değer vermeden davranışı değiştirmez (düzeltme turunda: değer verilmezse hiç kodlanmaz, S23) | ŞARTNAME | §7.3 |
| `SYSTEM_STARTED/STOPPED`, `MODEL_LOAD_FAILED`, `INFERENCE_DEVICE_FALLBACK` kodları | ŞARTNAME | §6.1 |
| KVKK hukuki dayanak iskeleti, geniş erişim günlüğü, model sürümü değişince gölgeye dönüş | ŞARTNAME | §5.7, §10 |

**Jürinin bulduğu ve bu belgede tekrarlanmayan hatalar** (önerilerdeki yanlış iddialar):

1. "Okuma zaman aşımı yoksa donan akış CAMERA_DOWN üretmez" **yanlış.** `KameraKaynagi.durum()`
   zamana bağlıdır (`kamera.py:119-136`); son kare zamanı yalnız başarılı `read()`'de
   güncellenir (`kamera.py:310`). Donan akış 60 sn sonra yine "çevrimdışı" olur ve olay
   yazılır (`supervizor.py:662-669`). Zaman aşımının kazancı **daha hızlı yeniden
   bağlanmadır**, algılama değil (bu belgenin §3.4 adım 1; docs/16 §8: FFmpeg varsayılanı 30 sn).
2. PowerShell → `winsound` değişikliği `tests/test_ses_cikisi.py:88-93`'ü kırar; R37 düzeltmesi
   `:160`'ı kırar. Yeni bölge tipleri `tests/test_hazir_kurallar.py:85` ve
   `tests/test_bolge_cizim_kolayligi.py:183`, `:195`'i kırar. Yasak alanı 1 sn'ye indirmek
   `test_hazir_kurallar.py:109-112`'yi kırar. Bu belge "tam paket değişmeden yeşil" demez; hangi
   testin bilinçli güncelleneceğini bu belgenin §4.6'sında yazar.
3. Komuta kabuğuna yalnız `uyari.js` eklemek yetmez: `EventSource`'u `canli.js:18` açar.
4. `?ses=1` diye bir parametre bugün kodda **yok**; kullanılacaksa eklenecek bir şeydir.
5. `TANINAN_SINIFLAR` sırası (`rules/tipler.py:35`: person, truck, forklift) §4.1 kimlikleriyle
   (1 forklift, 2 truck) çelişir; sıra kimlik olarak kilitlenmez (§4.1).
6. Windows'ta çalan sesi kesmek için `SND_PURGE` değil `winsound.PlaySound(None, 0)` kullanılır.
7. "ANALYSIS_DOWN bugün hiç olay üretmiyor" kısmen yanlış: tipli model hatası
   `supervizor.py:292`'de zaten sistem olayı yazıyor. Olay yazmayan yollar yalnız genel istisna
   (`:222-233`) ve veritabanı açılamaması (`:209-220`).
8. Kırpma sözleşmesi `kkd_siniflandirici.py:20-21`'dedir. `rules.severity` okunur
   (`supervizor.py:492` → `Kural.siddet`, `tipler.py:97`) ama hiçbir karar, renk ya da anons
   onu kullanmaz (`komuta.py:268-274` yorumu).
9. 0,35/0,28 ByteTrack eşik ayrışması bilinçli bir tasarım değil, supervision 0.25.1
   varsayılanının yan etkisidir; kodun belgelenmiş niyeti tersidir (`ayarlar.py:290-292`).
   Karar operatöre bırakıldı (S15).
10. GÖREV §8 numaraları: §8-2 AGPL sorusu, §8-4 kanal sorusudur. §16'da bunlar ayrı sütunda
    eşlenmiştir.

**Onay kapısı:** Faz 2'ye geçmeden operatör şunları onaylar: (a) §1'deki kararlar, (b) §16'da
"Gerektiği an: Faz 2 öncesi" yazan soruların cevabı ya da varsayılanın kabulü.

**Operatör için okuma sırası:** §1 (ne karar verildi) → §13 (her fazda ne göreceksiniz) →
§16 (sizin vereceğiniz kararlar). Geri kalanı yapay zekânın yol haritasıdır.

---

## 1. Kararlar özeti (tablo: konu · karar · gerekçe · CLAUDE.md ile ilişkisi)

| # | Konu | Karar | Gerekçe | CLAUDE.md ile ilişkisi |
|---|---|---|---|---|
| K1 | Süreç modeli | **Tek program.** Analiz, kamera okuma, bakım, bekçi ve anons işçileri aynı süreçte iş parçacığı | E6; docs/09 #1; süreç başına model belleği ve süreçler arası SQLite kilidi; Python 3.12'de çok iş parçacıklı süreçte `fork` uyarısı (docs/16 P29) | §4 ile aynı |
| K2 | Ayarların yeri | yaml yok. Nesne başına ayar ve **çalışırken açılıp kapanan her kapı** (KKD veri toplama kapısı, uyarı kanalları) SQLite'ta (5 sn damga ya da kullanım anında okuma, restart'sız, `supervizor.py:329-341`); süreç eşikleri `.env`'de (`ayarlar.py` tek okuyucu, restart ister); sözleşme sözlükleri (sınıf, bölge tipi, olay kodu) kodda; modelin sınıf eşlemesi ONNX dosyasının içinde. Docker'da `.env` salt okunur tek dosya bağlandığı için Ayarlar kaydı bugün çalışmaz (R27, `docker-compose.yml:24`, `ayarlar.py:433`); F2a'da dizin bağlamaya geçilir (§10.5) | E5; ikinci doğruluk kaynağı açılmaz; operatör dosya düzenlemez, Ayarlar sayfasını kullanır | §7 "eşik .env veya veritabanı" ile aynı; kalan sabitler Ç36 |
| K3 | Sınıf listesi | Kodda sabit kimlikli katalog 0–6 (§4.1). Hangi sınıfı ürettiğini model söyler: ONNX `custom_metadata_map`, yoksa bugünkü COCO eşlemesi (`tespit.py:26-36`) | Kimlik kalıcı olur (bugün sıra türevi, `takip.py:21`); ORT 1.19.2'de `ModelMetadata.custom_metadata_map` var (yerelde doğrulandı), hazır YOLOX dosyalarında boş | GÖREV §7 "kodda sabit sınıf listesi yasak" ile gerilim → §2 Ç12 |
| K4 | Bölge tipleri | Mevcut 6 DB kodu korunur; **+crossing, +ppe_exempt.** `zones` CHECK kısıtı 007'de kalkar. Kodların tek kaynağı saf katmanda `rules/tipler.py` `BOLGE_TIPI_KODLARI` (ve `ISTISNA_BOLGE_TIPLERI`); `web/ortak.py` `BOLGE_TIPLERI` yalnız bu kodlara Türkçe ad eşler, `kameralar.py:563-565` doğrulaması onu kullanır; eşitliği bir test korur (§4.5) | Yeniden adlandırma veri göçü ve `alan_bulucu.py:122-124` eşlemesini bozardı; CHECK her yeni tipte CASCADE tuzaklı tablo yeniden kurma ister (R24) | Uyumlu; CHECK kararı operatörde (S22) |
| K5 | Olay yaşam döngüsü | ACTIVE → RESOLVED durum makinesi `rules/olay_durumu.py`'de. **Cooldown değerlendiricilerde kalır**, `degerlendir()` çıktısı değişmez; olay sürerken tekrar gelen ihlal yeni satır açmaz, yalnız hatırlatma anonsu olur | Mühendis jürisinin aşısı: mevcut 85 kural testi dokunulmadan kalır | §6 saf katman korunur |
| K6 | Önem | `critical / high / medium / low` + sistem olayları için `system`. `rules.severity` canlanır; mevcut `'warning'` değeri "olay kodunun varsayılanı" demektir | Bugün sütun var ama ölü; göç gerekmez | Uyumlu |
| K7 | Takip hafızası | `.env TAKIP_HAFIZA_SN` (öneri 2) → `lost_track_buffer = hafıza × 30`. Yeni iz başlatma eşiği **bugünkü gibi** kalır | Olgu 8: hafıza bugün ~1 sn; eşik hizalaması operatör kararı (S15) | §7 "sabit eşik yok" |
| K8 | Kamera | RTSP açılış 5 sn / okuma 10 sn zaman aşımı (`kamera.py:223`); kamera bir kez çevrimiçi olduktan sonra `CAMERA_DOWN` 10 sn (`.env KAMERA_KOPUK_ESIGI_SN`); ilk bağlantıda 60 sn tolerans (belgelenmiş sabit, Ç36); `CAMERA_UP` için 5 sn kesintisiz kare (`.env KAMERA_UP_KARARLILIK_SN`; `durum()`'da değil süpervizörün olay üretiminde uygulanır) | §4.5; docs/16 §8 öneri 5; DOWN/UP seline karşı histerezis | Uyumlu; 10 sn eşiği S18 |
| K9 | Fail-safe sıra | Olay satırı yazılamasa **ya da kural satırı okunamasa** bile uyarı gönderilir; gölge ve anons kararı bellekteki kural haritasından verilir | Bugün `_kural_kaydi` (`supervizor.py:545` → `:570-580`) ya da `ihlal_yaz` (`:546`) hata verirse `duyur` (`:563`) hiç çağrılmıyor, istisna `:252`'de yutuluyor | §7 "tiplenmiş hata + log" |
| K10 | Bekçi | `analiz/bekci.py`; eşik 90 sn (docs/16 §8); tepki `BEKCI_TEPKISI` ile: `uyar` (varsayılan) ya da `yeniden_baslat` (yalnız Docker/systemd). Masaüstünde süreçten asla çıkmaz | Docker "unhealthy" container'ı yeniden başlatmaz; paketli masaüstünde çıkış Kontrol Paneli'ni de öldürür (`dalsan_launcher.py:975-979`) | Yeni servis değil, stdlib iş parçacığı |
| K11 | Sağlık ucu | `/saglik` **her zaman 200** ve `durum=calisiyor`; gövde genişler. `?hazirlik=1` ile hazır değilken 503. `/healthz` açılmaz | Kontrol Paneli 200 dışını "port başkasında" sayar (`dalsan_launcher.py:266-277`) | En az parça; §2 Ç16 |
| K12 | Metrik | `/saglik` JSON'u yeter. `/metrics` yalnız müşteride Prometheus varsa, elle yazılmış metin olarak | E7; `prometheus_client` eklenmez | §3 "yeni kütüphane yok" (S13) |
| K13 | Günlük | uvicorn'un üç logger'ı `loglama.py` JSON biçimleyicisine bağlanır | Olgu 5: uvicorn satırları bugün düz metin | Uyumlu |
| K14 | KKD yöntemi | İki aşamalı (docs/04 §2): kişi kırpığı → ONNX sınıflandırıcı, 2 baş (baret, yelek) × 3 sınıf (var / yok / görünmüyor). Eğitim ürün dışında, uzman işi ve tek seferlik; ürün içinde veri seti, değerlendirme ve HTML rapor kalır | Ucuz etiketleme, doğal "belirsiz", tespit modeline dokunulmaz | Ürüne torch girmez; docs/09 #7 ve CLAUDE.md §5 ile gerilim → Ç37 (S31) |
| K15 | KKD kararı | docs/04 penceresi korunur; **kalem başına olay** (`PPE_NO_HELMET` / `PPE_NO_VEST`); karar `bitis_s` boyunca belirsize dönerse olay kapanır; sürücü varsayılan muaf; kapsam varsayılanı "çizilen KKD bölgesi", `ppe_exempt` o bölgeden oyulur (hem sınıflandırıcıda hem veri örneklemede) | §4.8 kalem başına precision ister; docs/04:44 dahil etme modeli | §7 "belirsiz ihlal değil" olay süresinde de korunur |
| K16 | KKD devreye alma | Gölge mod zorunlu; kapı: kalem ve model sürümü başına precision ≥ `KKD_KAPI_PRECISION` (0,90, docs/04 §8.1), en az `KKD_KAPI_GUN` (3) gün, en az `KKD_KAPI_EN_AZ_OLAY` (öneri 30) incelenmiş olay ve **incelenmemiş olay kalmamış**; onaylanan model sürümü `rules.approved_model_version`'da (008); sürüm değişince kural gölgeye döner | docs/09 değişmeyen kararlar; docs/04 §8.2 "tüm olaylar incelenir" | Uyumlu |
| K17 | KKD veri toplama | Kapı SQLite'ta (007 `ppe_collection_gate`, tek satır), `.env`'de değil: çalışırken açılıp kapanır ve Docker'da da yazılabilir. Önerilen başlangıç `kapali` (S10). Açma, `/kkd`'de "Rev.02 imzalandı" onayıyla; açılış/kapanış sistem olayı. `_kkd_ornekle` her örnekten hemen önce kapıyı okur, yani kapatma gecikmesizdir. Yalnız KKD kuralının `min_person_height_px`'i (varsayılan 120) üstündeki kişiden örnek | Bugün toplama ön koşulsuz açık (`supervizor.py:582-638`); docs/00:63-64; `.env` restart ister (`ayar_rotalari.py:18`) ve Docker'da salt okunur (R27) | KVKK; K2 |
| K18 | Uyarı katmanı | Yeni `AlertChannel` yazılmaz. `AnonsYoneticisi` aynı adla evrilir: kanal başına tek işçi, öncelik kuyruğu, CRITICAL kesme, sağlık yoklaması | Olgu 3: soyutlama, bölgeler ve cooldown var | En az parça |
| K19 | Kanallar (bu tur) | Ekran (SSE), ses kartı (kablolu ya da Bluetooth sink), IP hoparlör (HTTP). Webhook (HMAC imzalı) **yalnız S4'te alıcı sistem varsa** kodlanır, yoksa docs/07. Ertelenen: mesajlaşma, ışıklı kule, SIP/ONVIF | E4; docs/07 #4; CLAUDE.md §2 | Yeni paket yok |
| K20 | Kanal sağlığı | 10 sn yoklama; 30 sn kesintisiz "koptu" → `AUDIO_CHANNEL_DOWN`; 2 ardışık "bağlı" → `AUDIO_CHANNEL_UP`. Linux'ta ses kartı satırı hedef sink adını **zorunlu** taşır; "boş = varsayılan" kalkar, çünkü varsayılanı denetlemek totolojiktir (§7.2). "Bilinmiyor" olay üretmez ama garantide sağlıklı sayılmaz | §4.6; olgu 3'teki üç kör nokta | Uyumlu |
| K21 | Garanti | Gölgede olmayan **her** güvenlik olayı (önemden bağımsız) en az bir **sesli/uzak** kanala (ses kartı, IP hoparlör, varsa webhook) "ok" ile ulaşmalı; ekran bu garantiye sayılmaz, ayrı gösterilir. Ulaşmazsa `ALERT_UNDELIVERED` (`ULASMAYAN_UYARI_ARALIGI_SN` hız sınırıyla) + CRITICAL günlük + `/saglik` `hazir=false` | §4.6; GÖREV §7 "Bluetooth tek kanal olamaz"; ekran kanalı kendi kendini doğrular (izleme penceresi açık kaldıkça "ok") | Uyumlu; Ç38 |
| K22 | Bölüm başına kanal | Kanal yapılandırmasının tek yeri `speaker_zones` (`kind`, `device`, 009). `.env ANONS`, `ANONS_SES_CIHAZI`, `ANONS_HTTP_ADRESI` 009 sonrası ilk açılışta bir kez "Tüm fabrika" satırına aktarılır ve emekliye ayrılır. Yeni kanal tablosu açılmaz | Aynı bilginin ikinci yeri olmaz; SQLite restart'sız ve Docker'da yazılabilir; R39 kendiliğinden kapanır | En az parça |
| K23 | Bluetooth | Eşleştirme işletim sisteminde kalır (E2, S8). Kopma algılanır (R37, `AUDIO_CHANNEL_DOWN`). Linux `bluetoothctl` yeniden bağlanma bekçisi **yalnız** S9'da hoparlörün kendiliğinden bağlanmadığı görülürse ve S29'da container'da ses yolu (A) ya da host kurulumu seçilirse yazılır; yoksa docs/07 | docs/14 §2.1.1; docs/16 §4 öneri 1 (MVP: varsayılan sink'e çal, kopmayı göster) | §3; §7 "ileride lazım diye" yok |
| K24 | Türkçe ses | İnsan kaydı WAV (`veri/sesler/`) + tarayıcı `tr-TR` + HTTP cihazın kendi TTS'i. Sunucu TTS yok | E3; tek Türkçe piper sesi ticari kullanılamaz (docs/16 §3) | §3 |
| K25 | Dağıtıcı sınırları | Dakika sınırı ve birleştirme penceresi **yalnız S23'te operatör değer verirse** kodlanır; yoksa docs/07. Bugünkü (kamera, mesaj) tekrar bastırması korunur, critical açılış ondan muaf | Operatör değer vermeden davranış değişmez; kapalı kod yazılmaz (CLAUDE.md §7) | Uyumlu |
| K26 | Kalibrasyonsuz mesafe | Pasif kalır (docs/03 §2, `motor.py:36`); etkin bir mesafe/hız kuralı kalibrasyon yüzünden pasifse `/saglik` `kritik_kural_pasif` ve kurulum listesinde kırmızı madde. Kalibrasyonlu ama kontrol ölçümü yapılmamış kamerada olay ve ekran "kalibrasyon doğrulanmadı" / "≈" der; kontrol ölçümü (S7 "evet" ise) olaya ölçülmüş hata %'sini yazar | Metre iddiası ya ölçülmüş hataya dayanır ya da açıkça "doğrulanmadı" diye işaretlenir | §2 Ç15 |
| K27 | Ölçüm altyapısı | İşlenen fps ve `isle()` süresi sayaçları; `analysis_hours`; `alert_deliveries`; sentetik senaryo takımı | §4.8 hedeflerinin paydası bugün yok | Uyumlu |
| K28 | KVKK | `docs/18-KVKK.md`; `hold`, `purge_log`, `access_log` (Faz 5; yasal yükümlülük karşılığı, kapalı özellik değil); ağ bölümlendirmesi belgesi; yüz bulanıklaştırma yalnız S27 "evet" ise kodlanır, o zaman da yalnız dışa aktarım ve KKD dışı kanıt; yüz tanıma ve ses işleme yok | docs/16 §7 | Uyumlu |
| K29 | Güvenlik | Faz 0 bulguları Faz 2'nin ilk adımında kapanır (XFF, şifre alanı, Origin + Host izin listesi, `/docs`, RTSP, PowerShell, `.env` satır enjeksiyonu ve Docker'da yazılamayan `.env` (R27), container'da şifresiz açılış (R13)) | Olgu 6 | Uyumlu |
| K30 | Çalışma zamanı | ORT 1.19.2 → 1.30.0 (S19); GPU için ayrı `requirements-gpu.txt` ve ayrı imaj, tek paket kuralı; supervision 0.25.1 sabit kalır; Python 3.12 (launcher üst sınırı `<3.13`) | Olgu 2; CVE-2026-14647; `sv.ByteTrack` 0.31'de kalkıyor | §4 teknoloji değişmez |
| K31 | Şema | 007 (Faz 2), 008 (Faz 3), 009 (Faz 4), 010 (Faz 5); numaralar birleşme sırasına göre verilir. Yabancı anahtarı kapatan betikten önce **otomatik yedek** | FK denetimi COMMIT'ten sonra koşuyor (`veritabani.py:134` → `:139`) | Uyumlu |
| K32 | Faz sırası | GÖREV §5 sırası korunur. Faz 3'ün modeli veriye bağlı olduğundan Faz 3'ün kod adımları bitince, model beklenirken Faz 4 başlar | Uyarı garantisi KKD verisini beklememeli | S28 |
| K33 | Kod adları | Yeni Python dosyaları komşularıyla tutarlı Türkçe (`olay_durumu.py`, `bekci.py`); DB sütunları, olay kodları, `.env` değerleri, metrik adları İngilizce | Kod tabanı Türkçe tanımlayıcı kullanıyor; CLAUDE.md'nin kendi §5 klasör/dosya düzeni de Türkçe (`ayarlar.py`, `analiz/`, `olaylar/`, `egitim/`) | §8 "kod içi isimler İngilizce" ile gerilim; öncelik kuralından bilerek sapma, gerekçe Ç27 (S26) |
| K34 | Olay klibi | Yok. Yol haritasında (ADR-009, docs/07 #1) | Kanıt fotoğrafı MVP akışına yeter; RAM, kodlayıcı, disk, KVKK hacmi | Altın kural |

---

## 2. Gereksinim ↔ CLAUDE.md çelişkileri ve çözümleri (tablo; operatöre bırakılanlar işaretli)

"Operatör" sütununda soru numarası olan satırlarda karar operatörün; tasarım varsayılanı
"Seçilen" sütunundadır.

| # | Gereksinim (GÖREV) | Çelişen karar | Seçilen | Gerekçe | Operatör |
|---|---|---|---|---|---|
| Ç1 | §4.9 kamera başına ayrı işçi süreci | CLAUDE.md §4 TEK program; docs/09 #1; E6 | Tek süreç + kamera başına `try/except` (`supervizor.py:527-532`) + bekçi | İzolasyon bugün var; eksik olan takılmanın fark edilmesi | — |
| Ç2 | §4.1/4.2/4.5/4.6 `config/*.yaml` | CLAUDE.md §7; E5 | SQLite + `.env` + kod sözlükleri + ONNX metadata | yaml ikinci doğruluk kaynağı olurdu; restart'sız yükleme yalnız SQLite'ta var | — |
| Ç3 | §4.11 REST + WebSocket | docs/01 §3.4 (SSE); E7 | SSE (`olaylar_web.py:98-142`) | Çift yönlü ihtiyaç yok | S13 (sözleşmede bağlayıcıysa) |
| Ç4 | §4.9 Prometheus | CLAUDE.md §3 yeni kütüphane yok | `/saglik` JSON; `/metrics` yalnız gerekirse, elle | docs/16 §8: biçim elle üretilebilir | S13 |
| Ç5 | §4.11 MQTT, §4.9 PostgreSQL v2 | CLAUDE.md §3; docs/09 #2 | İkisi de yol haritası; webhook MQTT'nin işini görür | En az parça | — |
| Ç6 | §4.6 piper / espeak-ng sunucu TTS | docs/14 §8; E3; lisans (docs/16 §3) | WAV + tarayıcı + HTTP cihaz TTS'i | Ticari kullanılabilir Türkçe piper sesi yok | S21 |
| Ç7 | §4.6 uygulama içi tara → eşleştir → güven → bağlan; otomatik yeniden bağlanma | docs/14 §2.1.1; E2; CLAUDE.md §7 "ileride lazım diye" | OS'ta eşleştirme; kopma algılanır; Linux yeniden bağlanma bekçisi S9/S29'a koşullu (K23) | PIN'li hoparlör etkileşimsiz eşleşmez; Windows diyaloğu bastırılamaz; hoparlör kendiliğinden bağlanıyorsa bekçi gereksiz parça | **S8**, S9 |
| Ç8 | §4.6 BlueZ D-Bus (`org.bluez`) | CLAUDE.md §3 | `bluetoothctl` alt süreci | `dbus-fast` yalnız alt süreç yetmezse | — |
| Ç9 | §4.6 ses seviyesi ayarı | docs/14 §8 "amfinin işi" | Yapılmaz | Bluetooth'ta amfi yok; ihtiyaç sahada görülürse | S9 |
| Ç10 | §4.6 `ip_speaker` SIP/ONVIF | docs/14 §8; E4 | Mevcut HTTP tetikleyici | — | — |
| Ç11 | §4.6 `assets/audio/tr/*.wav` | CLAUDE.md §5; docs/14 §2.3 | `veri/sesler/` | WAV müşteri varlığıdır, yedeğe girer; depoya ses girmez | — |
| Ç12 | GÖREV §7 "kodda sabit sınıf listesi yasak" | `tipler.py:35` sözlüğü | Sabit kimlikli **sözlük** kodda kalır (`BOLGE_TIPLERI` gibi); modelin ürettiği sınıflar model dosyasından okunur | Kimlik değişince kod da değişir; kullanıcı ayarı değildir | — |
| Ç13 | §4.3 `min_person_px` 60 | docs/04 §3 (baret 120 / yelek 80) | docs/04 | Baret kişi boyunun ~1/8'i; 60 px'te ~7 px kalır | — |
| Ç14 | §4.5 KKD "son 2 sn, ≥%70" | docs/04 §7 (15 değerlendirme, en az 8 geçerli, %75) | docs/04 | Bugünkü kadansla 2 sn'de ~2,4 gözlem düşer, 8 gerekir (§5.6); E10 | S16 |
| Ç15 | §4.5 kalibrasyonsuz piksel sezgisi + `confidence: low` | docs/03 §2, docs/08:47; `motor.py:36` | Pasif kalır; kontrol ölçümü eklenir | Yaklaşık metre üretilmez | S7 |
| Ç16 | §4.9 `/healthz` | Kontrol Paneli sözleşmesi (`dalsan_launcher.py:266-277`) | `/saglik` kalır; 503 yalnız `?hazirlik=1` ile | docs/16 §8 öneri 4'ün düz 503'ü paneli bozardı | — |
| Ç17 | §4.3 "`ppe_exempt` dışında her yer" | docs/04:44, docs/08 R9 (dahil etme) | Varsayılan dahil etme; `ppe_exempt` KKD bölgesinden oyulur; dışlama kipi seçenek | Dışlama kipi kırpık sayısını ve CPU'yu artırır (ölçülecek) | **S3** |
| Ç18 | §4.5/4.9 olay klibi 5+5 sn | ADR-009 (docs/05:105-108); docs/07 #1 | Yol haritası; `clip_path` sütunu açılmaz | RAM, kodlayıcı, disk, KVKK hacmi | S5 |
| Ç19 | §4.10 roller, klip izleme denetimi | docs/15 §7; docs/01 §3.6 (tek şifre) | Tek şifre kalır; Faz 5'te adres bazlı erişim günlüğü; roller docs/07 #5 | Altın kural | S5 |
| Ç20 | §4.10 "sırlar yalnız ortam değişkeninde" | docs/01 §3.1 kamera CRUD'u (RTSP şifresi SQLite'ta, `sema/001:21`) | RTSP şifresi DB'de, maskeli; webhook sırrı yalnız `.env` | Sapma belgelenir | — |
| Ç21 | §4.8 kamera başına ≥10 fps | docs/05 bütçesi 4 × 6 fps; E14 | 6 fps | Ölçüm: `tiny` %100, `s` %40 | — |
| Ç22 | §4.8 kare → ses ≤500 ms | E13: `yolox_s` CPU'da tespit p90 473–496 ms | Hedef donanıma koşullu; yazılım kısmı ölçülür, akustik kısım sahada | — | S1 |
| Ç23 | §4.7 `models/<ad>/<sürüm>/` kayıt defteri | CLAUDE.md §7 (`models/indir.sh`, ağırlık commit edilmez) | Düz `models/`; model kartı ONNX metadata'sında; sha256 `BILINEN_MODELLER`'de | Yeni klasör düzeni gerekmez | — |
| Ç24 | §4.7 Ultralytics, TensorRT, OpenVINO, INT8 | ADR-002 (YOLOX, Apache-2.0); CLAUDE.md §3 | YOLOX; hızlandırıcılar yol haritası | ORT sürüm yükseltmesi daha büyük kazanç (docs/16 §5) | S2 |
| Ç25 | §4.4 "ByteTrack ya da BoT-SORT" | CLAUDE.md §4 supervision ByteTrack | supervision 0.25.1 ByteTrack | `sv.ByteTrack` 0.28'de deprecated, 0.31'de kalkıyor | — |
| Ç26 | §5 `ARCHITECTURE.md`, `RUNBOOK.md`, `ANNOTATION.md`, `KVKK.md` adları | Numaralı Türkçe düzen; E8 | Bu dosya; saha kabul listesi docs/06'da; etiketleme kılavuzu docs/04 §5 + `docs/kkd-politika.md` (docs/04:249'da adı geçer); `docs/18-KVKK.md` | — | — |
| Ç27 | GÖREV §0-6 ve CLAUDE.md §8 "kod adları İngilizce" | Kod tabanı Türkçe tanımlayıcı kullanıyor; CLAUDE.md §5'in kendi dosya düzeni Türkçe | Yeni Python dosyaları Türkçe; şema, olay kodu, ayar değeri İngilizce | **Bu satırda §0'daki öncelik kuralından bilerek sapılıyor:** CLAUDE.md kendi içinde çelişik (§5 Türkçe dosya adları, §8 İngilizce isim kuralı) ve iki eşit öncelikli madde arasında kod tabanıyla tutarlılık seçildi. CLAUDE.md §8'in değiştirilmesi operatör onayına bağlıdır | **S26** |
| Ç28 | CLAUDE.md §4 Python 3.12 | `.venv` 3.11.15; ORT 1.19.2'nin 3.13+ tekerleği yok | Hedef 3.12; launcher üst sınırı `<3.13` (ORT sürümünden bağımsız); 3.13+ ancak tam paket orada yeşil koşunca açılır | docs/16: 1.30.0 ORT engelini kaldırır ama öteki paketler sınanmadı | S19 |
| Ç29 | CLAUDE.md §4 "fabrikada tek container" | Ses/BT host soketi ister (R36); GPU ayrı paket ister (E12) | Tek container korunur. Ses için varsayılan **(A)**: imaja `pulseaudio-utils`, host ses soketi bağlanır (§7.6); `/run/dbus:ro` yalnız BT bekçisi yazılırsa. GPU ayrı imaj değişkeni. systemd/host kurulumu varsayılan **değildir**: CLAUDE.md §4 değişikliği gerektirir, operatör kararıdır | CLAUDE.md §4 ve docs/09 #4 sabit; host'ta venv + systemd birimi + ayrı güncelleme yolu imaja tek apt paketi eklemekten fazla parçadır | **S1, S29** |
| Ç30 | docs/09 "CPU ile 3-4 kamera bile KKD için yetersiz" | Ölçüm: `tiny` 4 × 6 fps'i %100 karşılıyor | GPU gerekçesi `s` modeline ve KKD maliyetine bağlanır; KKD maliyeti ölçülecek | AUDIT-OLCUM §1.3 | S1 |
| Ç31 | CLAUDE.md §5 `egitim/` ve `modeller.py` var diyor | İkisi de yok | `egitim/` Faz 3'te açılır; `modeller.py` açılmaz, CLAUDE.md düzeltilir | — | — |
| Ç32 | §4.9 saklama varsayılanı 30 gün | `.env` 180/90 (`ayarlar.py:272-275`); KVKK'da sabit gün yok (docs/16 P28) | Varsayılan değişmez | Gün sayısını müşteri ve avukat belirler | S5 |
| Ç33 | §6 `tests/fixtures/videos` altında saha klipleri | KVKK ve Rev.02 (docs/00:63-64) | Sentetik video + senaryolu sahte dedektör; saha klibi depoya girmez | — | — |
| Ç34 | §4.5 `RESTRICTED_ENTRY` ≥1 sn | Hazır kural şema varsayılanı 2 sn (`parametreler.py:25`); `test_hazir_kurallar.py:109-112` | 2 sn kalır; 1 sn gölge ölçümüne bağlı | Yanlış alarm disiplini (docs/00:20-22) | S25 |
| Ç35 | CLAUDE.md §2 altın kural, §7 "ileride lazım diye" ↔ §4'ün tam kapsamı | GÖREV operatörün yeni isteği | Koşulsuz yapılanlar: doğrudan istenenler (sınıflar, yaya yolu, KKD, Bluetooth çıkışı ve kopma algısı), güvenlik tabanı, olay yaşam döngüsü, uyarı garantisi, KVKK yükümlülükleri. **Operatör cevabına koşullu** olanlar yalnız cevap "evet" ise kodlanır, aksi hâlde docs/07'ye satır olur: webhook (S4), dakika sınırı/birleştirme (S23), yüz bulanıklaştırma (S27), KKD dışlama kipi `muaf_disi` (S3), kalibrasyon kontrol ölçümü (S7), `/metrics` (S13), systemd bildirimi (S1), BT yeniden bağlanma bekçisi (S9, S29), KKD uyum istatistikleri (S34), uygulama içi eşleştirme (S8). Varsayılanlarla Bluetooth hoparlör fabrikada ancak S29 (A) sahada doğrulanırsa çalışır (imaj derlenmedi) | Kapsam sessizce daraltılmaz: her koşullu madde §16'da soru olarak durur | **S30** |
| Ç36 | CLAUDE.md §7 "sabit kodlanmış eşik yok" | AUDIT §7.2'deki sabitler ve bu tasarımın yeni eşikleri | **Kural:** güvenlik olayı üreten ya da bir arızanın ne kadar sürede görüneceğini belirleyen eşik `.env`'de ya da kural parametresinde durur. İç mekanik (zaman aşımları, JPEG kalitesi, HSV bantları, bakım aralıkları, NMS çarpanı, hız `dt` aralığı, kesik kutu payı, ilk bağlantı toleransı, UP için 2 ardışık yoklama) **belgelenmiş sabit** kalır ve §6.2 listesinde tek tek gerekçelenir | Hepsini `.env`'e taşımak Ayarlar sayfasını operatörün anlamayacağı onlarca satıra çıkarırdı; hiçbirini taşımamak §7'yi çiğnerdi | S36 |
| Ç37 | docs/09 #7 "tek komut → HTML rapor"; docs/09 "kurulu olacak tek şey Python"; CLAUDE.md §5 `egitim/ # veri seti, eğitim, HTML rapor` | Eğitim PyTorch, YOLOX depo klonu ve GPU ister (§5.8, §12.3) | Ürün içinde `egitim/`: veri seti dışa aktarımı + değerlendirme + **tek komutla HTML rapor** (ORT ile). Eğitimin kendisi operatör dışı, uzman işi, tek seferlik; kendi runbook'u docs/04 §6'ya yazılır; CLAUDE.md §5 açıklaması "eğitim ürün dışı" diye güncellenir | Ürüne torch girmez; operatörün makinesinde yalnız Python kalır | **S31** |
| Ç38 | GÖREV §7 "Bluetooth'un tek uyarı kanalı olması" yasak | Ekran kanalı her zaman var; dağıtıcının çalmayı reddetmesi güvenliği azaltır | Garanti ekranı saymaz (K21). Sesli kanalların tümü tek bir Bluetooth sink'iyse `/saglik` `tek_kanal_bluetooth`, sistem şeridi, Kontrol Paneli ve kurulum listesinde kırmızı; dağıtıcı yine çalar | Yasak biçimsel değil fiilen görünür kılınır; reddetmek hiç ses çıkmaması demekti | **S32** |
| Ç39 | GÖREV §4.6 `local_audio` "v1, varsayılan" ve "30 sn kopuksa `local_audio`'ya düş" | Bugün `ANONS=null` varsayılan (`.env.example:120`, `ayarlar.py:233`); sunucunun ses donanımı ve container ses yolu bilinmiyor | Yeni kurulumda kanal satırı yoksa ses çalmaz ama sessiz de kalmaz: `/saglik` `sesli_kanal_yok`, kurulum listesinde kırmızı. Bölümde sağlıklı kanal kalmazsa geri düşüş "Tüm fabrika" satırıdır; o da yoksa `yedek_ses_kanali_yok` | Varsayılan ses kartı, çalıcısı olmayan container'da 30 sn sonra sahte `AUDIO_CHANNEL_DOWN` üretirdi | S4 |
| Ç40 | §4.11 "KKD uyum istatistikleri (vardiya / gün / hafta)" | CLAUDE.md §2; KVKK 8770 (performans takibi meşru amaç değil) | Bu turda gölge karnesi + olay kodu başına yanlış alarm; uyum oranı (iz başına kararlı "var" / geçerli kararlı iz, kamera/bölge × gün/hafta, kişi kırılımı **yok**) yalnız S34 "evet" ise 008'de `analysis_hours`'a kalem sayaçlarıyla eklenir; vardiya kırılımı vardiya saatleri verilirse | Uyum oranı her kararlı izin sayılmasını ister (bugün yalnız ihlal yazılıyor) | **S34** |
| Ç41 | §4.11 "REST + WebSocket API" | E7; CLAUDE.md §3 | WebSocket yok (Ç3). Olay/kamera için ayrı JSON REST API açılmaz; bugünkü JSON uçlar (`/saglik`, SSE akışı, birkaç yardımcı uç, ör. `alan_rotalari.py:224`) ve CSV dışa aktarımı kalır; dışarıya itme webhook'la (S4) | Tüketicisi olmayan API ölü parçadır | S13 |
| Ç42 | §4.7 RT-DETR (PaddleDetection, Apache-2.0) adayı; "seçimi ölçülen doğrulukla gerekçelendir" | ADR-002 (YOLOX); CLAUDE.md §3 | YOLOX kalır. **Hiçbir adayın doğruluğu ölçülmedi**; seçim lisans + mevcut ORT hattı + hız ölçümüne (AUDIT-OLCUM §1) dayanır. YOLOX doğruluğu `tests/dogruluk_kiyas`'ta ölçülecek; §4.8 hedefi tutmazsa RT-DETR aynı takımla ölçülür (Paddle eğitim ortamı ürün dışı kalır) | Paddle ikinci bir eğitim çalışma zamanı demektir | S2 |
| Ç43 | §4.6 Windows'ta WASAPI ile cihaz seçimi | CLAUDE.md §3 (ek modül yok); docs/09 (fabrika Linux) | Windows'ta `winsound` işletim sisteminin varsayılan çıkışına çalar; cihaz seçimi yok, sağlık `None` (§7.7) | WASAPI ek paket/COM katmanı ister; Windows sunucu 7x24 için önerilmiyor | S1 |
| Ç44 | §4.5 kural alanı `zones` (çoğul) | `rules.zone_id` tek bölge (`sema/001`), 85 kural testi | Kural başına tek bölge kalır; çok bölge = bölge başına bir kural satırı (hazır kural düğmesi bölge başınadır) | Şema değişikliği `rules` tablosunu yeniden kurmayı ve CASCADE tuzağını (R24) ister | — |
| Ç45 | §4.7 `ANNOTATION.md` tespit kutusu kuralları (kesik nesne, örtüşme, kabin içi sürücü) ve tespit veri setinde kamera/gün ayrımı | Ç26 ve §5.8 yalnız KKD'yi kapsıyordu | Kutu etiketleme kuralı docs/04 §5'e "tespit kutuları" alt bölümü olarak eklenir; tespit ince ayarının birleştirme betiği (§12.3) de kamera+gün bölmesini zorlar | Aynı çekimin iki kümeye düşmesi ölçümü şişirir | S11 |
| Ç46 | §4.7 artırmalarda "yağmur" | docs/04 §6.2 listesinde yok | Artırma listesine yağmur eklenir (dış mekân rampası); docs/04 §6.2'ye satır | — | — |

---

## 3. Mimari (bileşenler, veri akışı, mevcut dosya karşılıkları dosya:satır; tek program modeli korunuyorsa iş parçacığı/bekçi tasarımı)

### 3.1 Tek paragraf

Bugünkü sistem §4'ün iskeletidir: tek süreç (`main.py:63` `app` → `uygulama.py:41`), tek
"analiz" iş parçacığı (`supervizor.py:58`), kamera başına okuma iş parçacığı (`kamera.py:95`),
saf kural motoru (`rules/motor.py:25-30`, 4 tip), SQLite (`sema/001–006`) ve üç anons adaptörü
(`anons.py:46`, `:103`, `:224`). v2 bu iskeleti değiştirmez. Eksik organlar mevcut dosyaların
içine konur: olay yaşam döngüsü, önem, bekçi, kanal sağlığı, gerçek KKD modeli. Yeni süreç ve
servis eklenmez; **eklenen parçalar** aşağıdaki envanterdedir ve her biri için "bu olmadan
olur mu" (CLAUDE.md §3) cevaplanmıştır.

| Parça | Tür | Nerede | Bu olmadan olur mu? | Koşul (yoksa docs/07) |
|---|---|---|---|---|
| `onnxruntime-gpu[cuda,cudnn]` + `backend/requirements-gpu.txt` + Dockerfile `ARG` ile ikinci imaj | pip paketi (nvidia CUDA/cuDNN tekerlekleri dahil) | Yalnız GPU imajı | `yolox_tiny` CPU'da bütçeyi %100 karşılıyor (pay yok); `s` modeli ve KKD için GPU gerekir (Ç30). Sistem CUDA'sı da olur ama host'a ayrı CUDA/cuDNN kurulumu ve sürüm eşleştirmesi ister; pip ekstrası her şeyi imajın içinde tutar (docs/16 §5) | S1: GPU doğrulanırsa |
| `pulseaudio-utils` (paket adı DOĞRULANMADI) | OS paketi | Fabrika imajı | Hayır, container'da ses kartı kanalı olmaz (R36); tek alternatif IP hoparlör | S29 (A) varsayılan |
| `bluez` istemcisi (`bluetoothctl`) + `/run/dbus:ro` | OS aracı (alt süreç) | Fabrika imajı / host | Evet, hoparlör kendiliğinden bağlanıyorsa; kopma yine algılanır | S9 + S29 |
| YuNet `2023mar` model dosyası | Model | `models/` (indirme, sha256) | Evet: önce modelsiz kutu üstü yöntemi denenir | S27 "evet" ve kutu üstü yetmezse |
| Eğitim ortamı (PyTorch, YOLOX depo klonu, ayrı venv) | Çalışma zamanı | **Ürün dışı**, uzman makinesi | Hayır, KKD sınıflandırıcısı ve forklift sınıfı eğitilemez; ama ürüne ve operatör makinesine girmez | Ç37, S31 |
| `analiz/bekci.py`, `rules/olay_kodu.py`, `rules/olay_durumu.py`, `egitim/` | Yeni Python dosyası (stdlib) | Ürün | Bekçi: hayır (R5); olay kodu/durumu: hayır (§4.5 olay sözlüğü ve yaşam döngüsü); `egitim/`: veri seti ve rapor için | — |
| sema 007–010 | SQL betiği | Ürün | Hayır (olay yaşam döngüsü, kanal, KVKK izleri) | Her göç onu kullanan fazla gelir |

Yeni pip paketi yalnız GPU imajındadır; CPU ürünü yeni kütüphane almaz.

### 3.2 Bileşen diyagramı

```
                 TEK SÜREÇ: uvicorn app.main:app (main.py:63; Dockerfile:40)
┌──────────────────────────────────────────────────────────────────────────────────┐
│ [asyncio] FastAPI  uygulama.py:41-138 · kimlik tek kapı uygulama.py:97-104       │
│   /olaylar/akis SSE   olaylar_web.py:98-142 ─▶ canli.js:18 ─▶ uyari.js (bant/bip) │
│   /saglik             rotalar.py:129-141  (F2: genişler, ?hazirlik=1 → 503)       │
│   (F2) Host izin listesi + Origin ara katmanı; /docs /redoc /openapi.json kapalı  │
│                                                                                    │
│ [N iş p.] KameraKaynagi  kamera.py:95/140  son kare + 1→30 sn geri çekilme        │
│           (F2) açılış/okuma zaman aşımı :223; kopukluk eşiği :50 ikiye ayrılır     │
│                 │ son_kare() (kamera.py:109)                                       │
│                 ▼                                                                  │
│ [iş p. "analiz"] AnalizSupervizoru._dongu supervizor.py:209  (F2) nabız damgası ──┐│
│   konfig damgası 5 sn :329-341 ◀── SQLite                                         ││
│   KameraHatti.isle boru_hatti.py:162                                               ││
│     Tespitci (tek oturum + kilit) tespit.py:159/:175                               ││
│     Takipci ByteTrack takip.py:32            (F2) lost_track_buffer                ││
│     KKD kırpık → sınıflandırıcı :286-310     (F3) ORT çıkarımı                     ││
│     KuralMotoru.degerlendir motor.py:106 ══ SAF rules/ ══                          ││
│       └ (F2) OlayDurumMakinesi rules/olay_durumu.py · kodlar rules/olay_kodu.py    ││
│   _ihlali_kaydet :544  (F2) önce kayıt dener, HATA OLSA DA duyurur                 ││
│   _durumlari_yaz :642  CAMERA_DOWN/UP (F2: kodlu, histerezisli)                    ││
│ [iş p. "bekci"]  (F2, yeni) analiz/bekci.py ◀──────────────────────────────────────┘│
│ [iş p. "bakim"]  supervizor.py:690-753 saklama + disk                               │
│ AnonsYoneticisi anons.py:275  bugün: anons başına 1 iş p. (:331)                     │
│   (F4) kanal başına 1 işçi + queue.PriorityQueue + "anons-saglik" yoklaması          │
└──────────────────────┬─────────────────────────────────────────────────────────────┘
   ses kartı / Bluetooth sink (paplay --device) · HTTP IP hoparlör · (F4, S4) webhook (HMAC)
Disk: veri/dalsan.db (WAL, veritabani.py:64) · veri/goruntuler/ · veri/sesler/*.wav · .env
```

### 3.3 İş parçacıkları (hepsi aynı süreçte)

| Ad | Adet | Bugün | v2 |
|---|---|---|---|
| uvicorn olay döngüsü + threadpool | 1 | var | aynı |
| `kamera-*` | kamera başına | `kamera.py:95` | + zaman aşımı, işlenen/okunan kare sayacı |
| `analiz` | 1 | `supervizor.py:58` | + her turda `time.monotonic()` nabız damgası, `isle()` süre halkası (p50/p90) |
| `bakim` | 1 (günde bir) | `supervizor.py:712` | Faz 5: `hold` olayına dokunmaz, `purge_log` yazar |
| `bekci` | 1 | yok | F2, 10 sn aralıkla |
| `anons` | anons başına bir tane | `anons.py:331` (sınırsız) | F4: kanal başına **bir** işçi (en çok hoparlör satırı + 2) |
| `anons-saglik` | 1 | yok | F4, `ANONS_SAGLIK_ARALIGI_SN` (10) |

İş parçacığı sayısı bugün sınırsızdır, çünkü her anons yeni bir daemon açar. v2'de sınırlıdır.

### 3.4 Bir ihlalin yolculuğu

| # | Adım | Bugün (dosya:satır) | v2 değişikliği | Faz |
|---|---|---|---|---|
| 1 | Okuma | `kamera.py:279` `read()`; son kare + monotonic zaman `:306-310` | `VideoCapture(url, CAP_FFMPEG, [OPEN_TIMEOUT_MSEC, 5000, READ_TIMEOUT_MSEC, 10000])` `.env`'den (docs/16 §8). Kazanç: donan akışta `read()` FFmpeg'in 30 sn varsayılanı yerine 10 sn'de döner ve yeniden bağlanma erken başlar; "çevrimdışı" kararı zaten zamana bağlıdır (`kamera.py:119-136`) | F2 |
| 2 | Örnekleme, geri basınç | `supervizor.py:516-524`, aynı kare atlanır | değişmez (§4.9 geri basınç zaten var) | — |
| 3 | Tespit + takip | `boru_hatti.py:181-185`; `takip.py:32` | `lost_track_buffer = int(TAKIP_HAFIZA_SN × 30)` | F2 |
| 4 | KKD gözlemi | `boru_hatti.py:286-310`; model yok → `:293` döner | ORT çıkarımı; kadans `.env KKD_KARE_ARALIGI` (bugün sabit `:49`); kırpık netliği | F3 |
| 5 | Kural | `supervizor.py:528` → `boru_hatti.py:189` → `motor.py:106-132` | kurala `simdi` yerine kare zamanı (R29); motor ayrıca `gecisleri_al()` verir: `acildi / hatirlatma / kapandi` | F2 |
| 6 | Kayıt | `supervizor.py:546` → `yazici.py:22-61` (fotoğraf önce) | `event_code`, `severity`; `kapandi` → `UPDATE events SET resolved_at`; hata olursa CRITICAL günlük ve adım 7 yine çalışır | F2 |
| 7 | Uyarı | gölge `supervizor.py:555`; `duyur` `:563` → `anons.py:307` | F4: dağıtıcı → bölümün TÜM kanalları → geri düşüş → `alert_deliveries` | F2/F4 |
| 8 | Ekran | SSE 1 sn yoklama `olaylar_web.py:108-134` | yük: kod, önem, `surduruyor/bitti`; biten olaylar ayrı sorguyla (`resolved_at` > son bakış; 007'deki kısmi olmayan `resolved_at` indeksiyle, yoksa her sekme her saniye tabloyu tarar; maliyet ölçülecek); komuta kabuğu da dinler | F2 |
| 9 | Sistem olayları | `supervizor.py:656-672`, `:292`, `:277`, `:748-753` | kodlu: CAMERA_DOWN/UP, VIDEO_FINISHED, DISK_LOW, MODEL_LOAD_FAILED, INFERENCE_DEVICE_FALLBACK, ANALYSIS_STALLED, ANALYSIS_DEGRADED, SYSTEM_STARTED/STOPPED; F4'te AUDIO_CHANNEL_DOWN/UP, ALERT_UNDELIVERED | F2/F4 |
| 10 | Konfig | arayüz → SQLite → 5 sn damga `supervizor.py:329-341` | damgaya `announcement_messages.updated_at` girer (R19); bunu yazan tek yol `anons_web.py:159` UPDATE'idir, oraya `updated_at = zaman.simdi_utc()` eklenir (bugün hiçbir yol yazmıyor) | F2 |

### 3.5 Fail-safe sırası (GÜVENLİK-ÖNCE aşısı)

Bugün `_ihlali_kaydet` önce `_kural_kaydi` ile kural satırını okur (`supervizor.py:545` →
`:570-580`, `SELECT * FROM rules`), sonra `ihlal_yaz`'ı çağırır (`:546`). Gölge mod (`:555`) ve
anons kimliği (`:558`) **yalnız bu okumadan** gelir; `Kural` nesnesinde gölge bilgisi yoktur
(`tipler.py:88-97`, `supervizor.py:482-493`). İki çağrıdan biri istisna fırlatırsa `duyur`
(`:563`) hiç çalışmaz ve hata `_dongu`'nun genel `except`'inde (`:252`) yutulur. Yani veritabanı
kilitliyken (`busy_timeout=5000`, `veritabani.py:68`) ihlal hem kayda geçmez hem duyurulmaz.
v2 sırası:

0. Süpervizör yapılandırmayı yüklerken (`_kurallari_yukle`, `:471-495`) bellekte bir
   `kural_id → (shadow_mode, announcement_id, severity)` haritası tutar. Bu harita motorun kural
   imzasına (`motor.py:76-86`) **girmez**; gölge açılıp kapanınca cooldown ve pencereler
   sıfırlanmasın diye. Harita 5 sn damgasıyla tazelenir.
1. `_kural_kaydi` **ve** `ihlal_yaz` tiplenmiş hatalarla (`sqlite3.Error`, `OSError`) `try`
   içinde denenir. `_kural_kaydi` başarısızsa olay kaydı bellekteki `Kural` ile (anlık görüntü
   eksik olarak) denenir.
2. Başarısızsa günlüğe CRITICAL yazılır ve `/saglik` `sorunlar` listesine `olay_yazilamadi`
   eklenir.
3. Gölge ve anons kararı bellekteki haritadan verilir. Gölge mod değilse uyarı **her durumda**
   dağıtıcıya gider. Faz 4'ten sonra teslim kaydı `alert_deliveries.event_id = NULL`,
   `event_code` dolu olarak yazılır.
4. Ekran kanalı SSE'yi veritabanı satırından beslediği için (`olaylar_web.py:108-134`) satır
   yazılamadıysa ekran uyarıyı göstermez; garanti zaten yalnız sesli/uzak kanallara dayanır
   (K21, §7.4).
5. `_ihlali_kaydet(baglanti, hat, ihlal, simdi)` ve `duyur(kamera_id, kamera_alani, zaman_s,
   mesaj)` imzaları korunur; yeni bilgi (olay kodu, önem, olay id, aşama) yalnız isteğe bağlı
   anahtar kelime argümanı `olay=None` olarak geçer (§7.1).

### 3.6 Bekçi (watchdog) tasarımı

- **Yer:** `backend/app/analiz/bekci.py`, stdlib `threading` (yaklaşık 60 satır).
- **Nabız:** `AnalizSupervizoru._dongu` her turda (`supervizor.py:255` 50 ms bekleme)
  `self.nabiz = time.monotonic()` yazar.
- **Takılma tanımı** (docs/16 §8): analiz iş parçacığı `is_alive()` değilse **ya da** en az bir
  kamera kare üretirken nabız `BEKCI_ESIGI_SN`'den (öneri 90, docs/16 §8) eskiyse. Model
  `yukleniyor` / `indiriliyor` evresinde bekçi saymaz. Eşik okuma zaman aşımından (10 sn) uzun
  tutulur.
- **Tepki:** `ANALYSIS_STALLED` sistem olayı (bekçinin kendi kısa bağlantısıyla, `anons.py:368`
  deseni), CRITICAL günlük, `/saglik` `hazir=false`. `BEKCI_TEPKISI=yeniden_baslat` ise ayrıca
  `os._exit(70)`; bu yalnız Docker (`restart: unless-stopped`, `docker-compose.yml`) ve systemd
  (`Restart=always`) kurulumunda anlamlıdır. Paketli masaüstünde (`dalsan_launcher.py:975-979`
  aynı süreç) bekçi **her durumda** yalnız uyarır.
- **Ölü iş parçacığı:** `is_alive()` False ise süpervizör yeniden kurulmaz (aynı hatayla tekrar
  ölür); olay + uyarı + gerekiyorsa çıkış. Takılan iş parçacığı Python'da öldürülemez; tek çare
  süreç yeniden başlatmadır.
- **Kamera başına hata sınırı:** `_kameralari_isle`'deki `except` (`supervizor.py:529-532`)
  ardışık hata sayar; sayaç `.env ANALIZ_HATA_ESIGI`'ni (öneri 30) aşınca o kameranın hattı
  (`KameraHatti`) yeniden kurulur ve `ANALYSIS_DEGRADED` yazılır. Değer sahada ayarlanır.
- **systemd bildirimi (yalnız S1 "systemd" ise, F5):** varsayılan dağıtım Docker tek
  container'dır ve `NOTIFY_SOCKET` Docker'a taşınmaz (docs/16:660); bu yüzden kod varsayılan
  olarak **yazılmaz**, docs/07'ye satır olur. S1 systemd derse en az parçalı biçim:
  `Type=simple` + `WatchdogSec=120` + `NotifyAccess=main` ve stdlib soketle yalnız
  `WATCHDOG=1` (systemd'nin MIT-0 örneği). `Type=notify` seçilmez: o zaman `READY=1` de
  gönderilmek zorundadır, gönderilmezse systemd başlatmayı `TimeoutStartSec` sonunda başarısız
  sayar (docs/16:622) ve §4.9'un "açılışta başlama" maddesi yeniden kırılır. `sdnotify` paketi
  eklenmez. R26 (`app.main:app`) bundan bağımsızdır ve F2a'da düzeltilir.

### 3.7 Yapılandırma yayılımı

| Nitelik | Nerede | Restart |
|---|---|---|
| Kamera, bölge, kural, kalibrasyon, hoparlör/kanal satırı (tek yer, K22), anons metni | SQLite | Hayır (5 sn damga) |
| KKD veri toplama kapısı | SQLite `ppe_collection_gate` (007) | Hayır; her örnekten önce okunur |
| Süreç düzeyi eşik ve sırlar | `.env` → `ayarlar.py`; ekranda Ayarlar sayfası (`ayar_rotalari.py`). Docker'da `.env` F2a'dan sonra dizin olarak bağlanır (R27) ki Ayarlar kaydı çalışsın | Evet |
| Sınıf kimliği, bölge tipi adı, olay kodu, önem adı | Kod (`rules/tipler.py`, `rules/olay_kodu.py`, `web/ortak.py`) | Kod değişikliği |
| Modelin ürettiği sınıflar, sürüm, veri penceresi | ONNX `custom_metadata_map` | Model değişince |
| Bluetooth eşleşme ve güven anahtarları | İşletim sistemi (BlueZ, `/var/lib/bluetooth`) | — |

Yeni `.env` anahtarları (hepsi Ayarlar sayfasına Türkçe açıklamayla girer; `tests/test_ayarlar.py`
iki yönlü eşitliği korur). `Ayarlar` `@dataclass(frozen=True)` ve alanları varsayılansızdır
(`ayarlar.py:39-70`); `tests/conftest.py:92-136` onu bütün alanları tek tek vererek kurar. Bu
yüzden yeni alanlar dataclass'ın **sonuna varsayılanlı** eklenir; böylece `conftest.py` yalnız
değeri testte farklı olması gereken alanlar için güncellenir (ör. Host izin listesine
`testserver`):

| Faz | Anahtar (varsayılan) |
|---|---|
| F2 | `TAKIP_HAFIZA_SN` (2, öneri) · `KAMERA_KOPUK_ESIGI_SN` (10, §4.5) · `KAMERA_UP_KARARLILIK_SN` (5) · `RTSP_ACILIS_ZAMAN_ASIMI_MS` (5000) · `RTSP_OKUMA_ZAMAN_ASIMI_MS` (10000) · `BEKCI_ESIGI_SN` (90) · `BEKCI_TEPKISI` (`uyar`) · `KKD_KARE_ARALIGI` (5, bugünkü `boru_hatti.py:49`) · `ANALIZ_YAVAS_SURE_SN` (60, öneri; `ANALYSIS_DEGRADED`) · `ANALIZ_HATA_ESIGI` (30, öneri) · `IZINLI_SUNUCU_ADLARI` (boş; `127.0.0.1`, `localhost` ve `SUNUCU_ADRESI` her zaman izinli, R8) |
| F3 | `KKD_MODEL_DOSYASI` (boş = model yok) · `KKD_KAPI_PRECISION` (0,90, docs/04 §8.1) · `KKD_KAPI_GUN` (3) · `KKD_KAPI_EN_AZ_OLAY` (30, öneri; S33) |
| F4 | `ANONS_SAGLIK_ARALIGI_SN` (10, §4.6) · `ANONS_KOPUK_ESIGI_SN` (30, §4.6) · `ULASMAYAN_UYARI_ARALIGI_SN` (300, öneri; `ALERT_UNDELIVERED` hız sınırı) |
| F5 | `DISK_DUR_GB` (1, öneri; S35) |
| Koşullu | `ANONS_DAKIKA_SINIRI`, `ANONS_BIRLESTIRME_SN` (S23) · `WEBHOOK_ADRESI`, `WEBHOOK_SIRRI` (S4) · `YUZ_BULANIKLASTIRMA` (S27) · `METRIK_ANAHTARI` (S13; `/metrics` Bearer) |
| Emekli (F4) | `ANONS`, `ANONS_SES_CIHAZI`, `ANONS_HTTP_ADRESI`: 009'dan sonraki ilk açılışta bir kez "Tüm fabrika" `speaker_zones` satırına aktarılır (K22); sonra okunmaz, `.env.example`'dan ve Ayarlar sayfasından kalkar. `ANONS_HTTP_BICIMI` ve `ANONS_BEKLEME_SN` süreç düzeyi olarak kalır |

Kaldırılanlar: `KKD_VERI_TOPLAMA` (kapı SQLite'ta, K17), `KKD_BULANIKLIK_ESIGI` (eşiğin tek yeri
kural parametresi `min_netlik`, K2), `BT_YENIDEN_BAGLAN` (bekçi yalnız gerektiğinde yazılır ve
o zaman bluez sink'lerinde hep çalışır; açma anahtarı gereksiz parça).

Sayım: bugün 33 anahtar (`.env.example`). Koşulsuz 19 yeni, 3 emekli → **49**; koşullu 6'nın
hepsi açılırsa 55.

### 3.8 Dosya değişiklik haritası

| Dosya | Değişiklik | Faz |
|---|---|---|
| `rules/tipler.py` | `SINIF_KATALOGU` (sabit kimlik 0–6); `TANINAN_SINIFLAR` ondan türer. `BOLGE_TIPI_KODLARI` ve `ISTISNA_BOLGE_TIPLERI` (bölge tipi kodlarının tek kaynağı; bugün yalnız yorum, `:73-74`). `Ihlal`'e `olay_kodu`, `siddet` varsayılanlı alanlar; `KkdGozlem`'e `netlik: float \| None` | F2/F3 |
| `rules/olay_kodu.py` (yeni) | Saf eşleme: (kural tipi, bölge tipi, hedef sınıflar, `mode`, KKD kalemi) → (olay kodu, varsayılan önem); bağlamsal yükseltme | F2 |
| `rules/olay_durumu.py` (yeni) | `OlayDurumMakinesi`: anahtar başına ACTIVE→RESOLVED, `bitis_s`, kapanış sebepleri | F2 |
| `rules/motor.py` | `gecisleri_al()`; değerlendiricilerin `aktif_anahtarlar()`'ını toplar; kural imzasına (`:76-86`) `siddet` girer | F2 |
| `rules/bolge_ihlali.py`, `mesafe.py`, `hiz.py`, `kkd.py` | `aktif_anahtarlar()` (çıkış eşiğiyle); kayıp toleransı kurucudan (verilmezse bugünkü 5); geçit istisnası; mesafede R21 ve `histerezis_m`; KKD'de kalem başına olay, sürücü, `ppe_exempt`, netlik | F2/F3 |
| `rules/parametreler.py` | `bitis_s`, `gecit_haric`, `histerezis_m`; F3: `surucu_muaf`, `min_netlik` (None = kapalı), `max_kisi_ortusmesi` (None = kapalı), `surucu_ortusme_orani`; `kapsam` yalnız S3 dışlama kipini seçerse — varsayılanlar bugünkü davranışı korur, `tests/rules/test_kkd.py` değişmez | F2/F3 |
| `analiz/takip.py` | `lost_track_buffer`; sınıf numarası katalog kimliğinden (`:21`); isteğe bağlı başlatma eşiği kurucu parametresi (yalnız kabul takımı için, S15); `:30` yorumu düzeltilir | F2 |
| `analiz/kamera.py` | `:223` zaman aşımları; `:50` ikiye ayrılır (ilk bağlantı toleransı 60, belgelenmiş sabit / kopukluk `KAMERA_KOPUK_ESIGI_SN` 10). UP kararlılığı burada **değil**, süpervizörün olay üretiminde (`durum()` tek karar noktası kalır) | F2 |
| `analiz/boru_hatti.py` | `isle()` süresi halkası; kare zamanı; `:49` `.env`'den; `kkd_bolgesinde_mi` (`:276-282`) `ppe_exempt` poligonlarını düşer; bu fonksiyon hem sınıflandırıcıyı (`:302`) hem veri örneklemeyi (`supervizor.py:591`) kapılar. F3: netlik; kişi örtüşmesi; `muaf_disi` kipi yalnız S3 seçerse | F2/F3 |
| `analiz/supervizor.py` | nabız; fail-safe sıra (`:544-580`) ve bellek kural haritası (§3.5); geçişlere göre INSERT/UPDATE/hatırlatma; açılışta ve kapanışta açık olayları kapatma; kodlu sistem olayları; `_durumlari_yaz` (`:642`) CAMERA_UP için `KAMERA_UP_KARARLILIK_SN`; `analysis_hours` yazımı; `:90` → `KKD_MODEL_DOSYASI`; `_kkd_ornekle` (`:582`) her örnekten önce `ppe_collection_gate`'i okur ve piksel sınırını KKD kuralının `min_person_height_px`'inden alır; `_kalibrasyonu_yukle` (`:497-507`) kontrol hatasını da okur (S7); F3: onaylı model sürümü karşılaştırması (§5.7) | F2/F3 |
| `analiz/bekci.py` (yeni) | §3.6 | F2 |
| `analiz/kkd_siniflandirici.py` | `NotImplementedError` (`:56-59`) yerine ORT oturumu; `model_surumu` = dosya adı + sha256'nın ilk 12 karakteri | F3 |
| `analiz/tespit.py` | sınıf eşlemesi metadata'dan; EP hatası ile bozuk dosya ayrımı (`:103-117`); iki ORT paketi birlikte kuruluysa uyarı | F2/F3 |
| `analiz/model_indir.py`, `models/indir.sh` | `BILINEN_MODELLER` `{ad: sha256}` (R17) | F2 |
| `olaylar/yazici.py` | `event_code`, `severity`; yeni `olay_bitir()`; `sistem_olayi_yaz` kod ve önem alır | F2 |
| `olaylar/anons.py` | F2: Windows'ta `winsound`. F4: `saglik()`, kanal işçileri, öncelik kuyruğu, kesme, sağlık yoklaması, teslim kaydı, `.env ANONS*` → "Tüm fabrika" satırı tek seferlik aktarımı; `WebhookAnonscu` yalnız S4 "evet" ise. `_cal_ve_kaydet` tek kanal çal+kaydet olarak korunur; `_hedef_anonscu` ve `_anonscu` kanal satırlarına geçer | F2/F4 |
| `olaylar/ses_cihazlari.py` | R37: boş seçim artık `True` değil `None`; ses kartı satırı hedef sink adını zorunlu taşır; bluez sink'inde eşleşme adres deseniyle (profil soneki değişebilir); sink adından MAC; `bluetoothctl` yardımcıları yalnız S9/S29 bekçisi yazılırsa | F4 |
| `web/giris.py` | XFF (`:87-97`); bayt karşılaştırma (`:197`) | F2 |
| `uygulama.py` | Host izin listesi + Origin ara katmanı (§10.5 R8); `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)` (`:93`); lifespan'de bekçi, SYSTEM_STARTED/STOPPED | F2 |
| `ayarlar.py`, `.env.example` | §3.7 anahtarları (dataclass sonuna, varsayılanlı); `_env_degeri` (`:401-410`) `\n`/`\r` reddi (R14); `.env` yolu `resolve()` ile çözülür, geçici dosya hedefle aynı dizinde oluşur (R27) | F2–F5 |
| `tests/conftest.py` | Yeni `Ayarlar` alanlarının testte farklı olanları (Host izin listesinde `testserver`) | F2 |
| `web/ayar_rotalari.py`, `templates/komuta_ayarlar.html` | şifre alanı (`:95-100`, `:48`) | F2 |
| `web/rotalar.py` | `/saglik` (`:129-141`) | F2/F4 |
| `web/ortak.py` | `BOLGE_TIPLERI` (`:17-24`) +2, kodları `rules/tipler.BOLGE_TIPI_KODLARI`'ndan; olay kodu/önem adları; `olay_hazirla` (`:222-261`); `EK_HAZIR_KURALLAR`; `HazirKural` (`:302-317`) yeni `golge: bool = False` alanı; `BOLGE_ZORUNLU_KURALLAR` (`:35`) yalnız S3 dışlama kipini seçerse gevşer | F2 |
| `web/kurallar.py`, `web/kameralar.py` | ek hazır kural ekleme; `hazir_kural_ekle` INSERT'i (`kurallar.py:246-259`) `shadow_mode` yazar (bugün yazmıyor, DEFAULT 0); "bölgede zaten kural var" denetimi (`kurallar.py:233`) ek hazır kural için (bölge, tip, hedef) üçlüsüne daralır; formda önem ve yeni alanlar; önem olay kodunun varsayılanının altına indirilirse uyarı; `kameralar.py:98` `Form(6)` yerine `.env KARE_ORNEKLEME_FPS` (bugün okunmuyor, AUDIT §7.2); `kameralar.py:453-465` yeniden kalibrasyonda `check_*` sütunlarını NULL yapar (S7); `kurallar.py:129` bölgesiz KKD'yi yalnız `muaf_disi` kipinde kabul eder (S3) | F2 |
| `web/olaylar_web.py` | SSE yükü; istemci sayacı; filtreler | F2/F4 |
| `web/komuta.py` | `_olay_rengi` (`:275`) önemden; sağlık ekranı (`:756`); gölge kapısı (`:207`) | F2/F3 |
| `web/static/uyari.js`, `canli.js`, `kamera_detay.js`, `stil.css`; `templates/komuta_temel.html` | §11; bütün şablonlardaki ortak `?v=N` (bugün `?v=24`) birlikte artırılır | F2 |
| `web/anons_web.py` | F2: `:159` UPDATE'i `updated_at` yazar (R19). F4: §11 | F2/F4 |
| `web/hoparlorler.py`, `web/kkd_web.py`, `web/kilavuz.py` | §11; `hoparlorler.py:32-45` loopback/link-local reddi (R30) F4a'da, sağlık yoklaması da aynı doğrulamadan geçer | F2 (kapı), F3/F4 |
| `egitim/__init__.py`, `egitim/veri_seti.py`, `egitim/degerlendirme.py` (yeni) | §5.8 | F3 |
| `loglama.py` | uvicorn logger'ları | F2 |
| `veritabani.py` | FK-kapalı betik öncesi otomatik yedek, yalnız kurulu bir veritabanında (§8.4) | F2 |
| `tests/test_veritabani.py` | `_eski_kurulum` (`:132-139`) yalnız verilen önekten ÖNCEKİ betikleri kopyalar (§8.4); mesaj sayısı şemadan türetilir | F2 |
| `sema/007…010` (yeni) | §8 | F2–F5 |
| `Dockerfile`, `docker-compose.yml`, `backend/requirements*.txt` | healthcheck; `.env` tek dosya yerine dizin bağlama (R27, F2a); container'da şifresiz açılış reddi (R13, F2a); ses bloğu (S29 (A)); GPU imajı; ORT sabiti | F2/F4/F5 |
| `masaustu/dalsan_launcher.py` | Python üst sınırı `(3,12) <= v < (3,13)` (`:209`); `hazir=false` / `uyari_garantisi` satırı | F2 |
| `docs/03`, `docs/04`, `docs/06`, `docs/07`, `docs/14`, `docs/kkd-politika.md`, `docs/18-KVKK.md`, `CLAUDE.md` | §13'te fazına göre | F2–F5 |

---

## 4. Sınıflar ve bölgeler (kapalı sınıf listesi ve id'ler; bölge tipleri; ayak noktası; saklama yeri)

### 4.1 Kapalı sınıf listesi

`rules/tipler.py`'de yeni `SINIF_KATALOGU`. Kimlik **asla** değişmez; yeni sınıf sona eklenir.
Takip katmanı sınıf numarasını bugün `TANINAN_SINIFLAR` sırasından üretiyor (`takip.py:21`);
v2'de katalog kimliğinden üretir. Bugünkü sıra (person, truck, forklift) kimlik olarak
kilitlenmez, çünkü §4.1 ile çelişir.

| id | kod | Arayüz adı | Bugün üretiliyor mu | Nasıl gelecek |
|---|---|---|---|---|
| 0 | `person` | İnsan | Evet (COCO 0) | — |
| 1 | `forklift` | Forklift | **Hayır** (`TANINAN_SINIFLAR`'da var, model üretmez) | LOCO (CC0) + saha verisiyle YOLOX ince ayarı (§12.3) |
| 2 | `truck` | Tır / kamyon | Evet, ama COCO car + bus + truck birleşik (`tespit.py:26-36`) | İnce ayarla ayrılır |
| 3 | `loader` | Yükleyici / kepçe | Hayır | Açık veri **yok**; yalnız saha verisi (S12) |
| 4 | `pallet_jack` | Transpalet | Hayır | LOCO "pallet truck" |
| 5 | `car` | Binek / pikap | Hayır (bugün "truck"a katılıyor) | İnce ayarla ayrılır |
| 6 | `pallet` | Palet | Hayır | §4.1: v2, isteğe bağlı |

Arayüz (kural formu, renk anahtarı) yalnız **aktif modelin ürettiği** sınıfları gösterir;
kullanıcı hiç görünmeyecek bir sınıfa kural kuramaz. `web/ortak.py:45` (`SINIFLAR`),
`tespit.py` `SINIF_TR` ve `SINIF_OVERLAY` Türkçe/ASCII adları katalogla bir testle eşit tutulur.
Arayüz, model ayırana kadar "Tır/Araç" demeye devam eder.

### 4.2 Model → sınıf eşlemesi

- **Özel model:** eğitim betiği ONNX dosyasına `custom_metadata_map` içinde
  `dalsan_classes` anahtarını yazar (çıkış indeksi → katalog kodu). `Tespitci` bunu
  `session.get_modelmeta()` ile okur. ORT 1.19.2'de bu özellik var (yerelde doğrulandı).
- **Hazır YOLOX (`yolox_tiny.onnx`, `yolox_s.onnx`):** metadata boş; bugünkü COCO eşlemesi
  (`tespit.py:26-36`) kullanılır.
- Metadata'daki bir kod katalogda yoksa tespit atlanır ve bir kez günlüğe yazılır (bugünkü
  `takip.py` `_bilinmeyeni_bildir` deseni).

### 4.3 Bölge tipleri

| §4.2 adı | DB kodu (değişmez) | Türkçe | Durum | Kullanıldığı yer |
|---|---|---|---|---|
| `walkway` | `pedestrian_path` | Yaya yolu | var | yaya yolu dışı kişi (bugünkü hazır kural), yaya yolunda araç (yeni ek hazır kural) |
| `vehicle_lane` | `vehicle_area` | Araç sahası | var | güvenli mesafe (bugünkü hazır kural), araç yolunda yaya (yeni ek hazır kural) |
| `crossing` | `crossing` | Yaya-araç geçidi | **yeni** | istisna: ayak noktası geçitteyse bölge ihlali sayılmaz (`gecit_haric`, varsayılan açık) |
| `loading_dock` | `loading_area` | Yükleme alanı | var | yükleme alanında yaya |
| `restricted` | `restricted` | Yasak bölge | var | yasak alana giriş |
| `ppe_exempt` | `ppe_exempt` | KKD muaf alan | **yeni** | KKD bölgesinden oyulur (kabin, ofis köşesi); dışlama kipinde kapsam dışı |
| — | `truck_parking` | Tır park alanı | var | araç konum dışında |
| — | `ppe_required` | KKD zorunlu alan | var | KKD kuralı |

Yeni iki tipin hazır kuralı yoktur, çünkü kendileri kural değil istisnadır.

### 4.4 Ayak noktası

Karar noktası kutunun alt-ortasıdır: `Tespit.ayak_noktasi()` (`tipler.py:63-67`), normalize
edilip stdlib ışın yöntemiyle poligon testi (`rules/geometri.py`) yapılır. §4.2 bunu zaten
karşılıyor; `PolygonZone` eklenmez (docs/16 §6: cv2 yasağı ve piksel koordinatı).

### 4.5 Saklama yeri

- Bölgeler SQLite `zones` tablosunda, normalize (0–1) çokgen JSON (`sema/001:45-55`), arayüzden
  çizilir (`kamera_detay.js`), 5 sn damgayla restart'sız uygulanır.
- `zone_type` CHECK kısıtı (`sema/001:50-52`) 007'de kalkar; tek süzgeç
  `kameralar.py:_bolge_tipi_dogrula` (`:563-565`). Neden: her yeni tipte `zones`'u yeniden
  kurmak `rules.zone_id … ON DELETE CASCADE` tuzağını (R24) tekrar tekrar açar. Bedel:
  veritabanı düzeyindeki ikinci güvenlik ağı gider. Bunu telafi için süpervizör bölge
  yüklerken bilinmeyen tipi günlüğe yazar ve atlar. Karar operatöre soruldu (S22).
- **Kodların tek kaynağı `rules/tipler.py`'dir, `web/ortak.py` değil.** `rules/` katmanı
  (geçit istisnası, `ppe_exempt` oyma, olay kodu eşlemesi) bu kodlara ihtiyaç duyar ama
  `app.web`'i import edemez (`tests/rules/test_saflik.py:33`, `:60`: izinli yalnız `app.rules`
  ve `app.hatalar`; `ortak.py:11` modül düzeyinde FastAPI import eder). Analiz katmanı da bugün
  `app.web`'i hiç import etmiyor. Bu yüzden `BOLGE_TIPI_KODLARI` ve `ISTISNA_BOLGE_TIPLERI`
  saf katmanda durur; `web/ortak.BOLGE_TIPLERI` bunlara yalnız Türkçe ad eşler (web → rules
  yönü zaten kullanılıyor, `ortak.py:14`). Süpervizör süzgeci ve `rules/` bu sabiti kullanır;
  bir test iki tarafın anahtar kümesinin eşitliğini korur. 007 yorumu buna göre yazılmıştır.

### 4.6 Bilinçli güncellenecek testler

Bu değişiklikler mevcut testleri kırar. "Testi devre dışı bırakarak yeşile çekmek" yasaktır
(GÖREV §7); her biri gerekçesiyle commit mesajına yazılır:

| Test | Neden kırılır | Ne yapılır |
|---|---|---|
| `tests/test_hazir_kurallar.py:85` (`set(HAZIR_KURALLAR) == set(BOLGE_TIPLERI)`) | `crossing`, `ppe_exempt` hazır kuralsız | `rules/tipler.ISTISNA_BOLGE_TIPLERI` kümesi tanımlanır; test "istisna dışındaki her tipin hazır kuralı var" olur |
| `tests/test_veritabani.py:56` (`mesajlar == 5`) | 007 üç yeni mesaj tohumlar (§8.2) | Beklenen sayı `tests/sema_bilgisi.py` desenindeki gibi şema betiklerinden türetilir (ör. tohum `INSERT` satırları sayılır), elle 8 yazılmaz |
| `tests/test_veritabani.py:59-63` (anahtar kümesi tam 5'li) | Aynı | Kümeye `vehicle_on_walkway`, `person_in_vehicle_lane`, `restricted_entry` eklenir |
| `tests/test_komuta_kabugu.py:102-106` (`"… · 5 hazır mesaj"`) | Aynı | Sayı veritabanından okunup metne konur |
| `tests/test_kamera_kaynagi.py:32-39` | Kopukluk eşiği 60'tan `KAMERA_KOPUK_ESIGI_SN`'e (10) iner; son kareden 59 sn sonra `ONLINE` beklentisi (`:36`) kırılır | İlk bağlantı toleransı ve kopukluk eşiği iki ayrı sabitle sınanır. UP kararlılığı `durum()`'a konmadığı için `:35` (1 sn sonra ONLINE) korunur |
| `tests/test_platform_uyumu.py:200-212` (`test_powershell_kesme_isareti_kacirilir`) | winsound yolunda alt süreç komutu yok; `_ses_komutu` win32'de komut döndürmez | Test "Windows'ta `winsound.PlaySound` çağrılır, alt süreç açılmaz" olarak yeniden yazılır; gerekçe commit mesajına |
| `tests/test_anons_baglama.py:116` (`_hedef_anonscu`), `tests/test_uyari_ve_anons.py:196` (`yonetici._anonscu`) | İç API: F4'te kanal satırlarına geçilince ikisi de kalkar | F4'te kanal işçisi üzerinden yeniden yazılır |
| `tests/test_platform_uyumu.py:195` (`_cal_ve_kaydet`) | İç API korunur (§7.1), ama beklenen metin `"ANONS=null"` F4'te emekli anahtarı anar | Beklenen metin "sesli kanal tanımlı değil" olur |
| `.env ANONS` / `ANONS_SES_CIHAZI` / `ANONS_HTTP_ADRESI`'ye bağlı testler: `conftest.py`, `test_anons_baglama.py`, `test_ayarlar.py`, `test_ayarlar_sayfasi.py`, `test_kilavuz_ve_kurulum.py`, `test_komuta_kabugu.py`, `test_komuta_uyari_ve_anons.py`, `test_paketlemeye_hazirlik.py`, `test_platform_uyumu.py`, `test_ses_cikisi.py` (10 dosyada ~40 satır; `grep` ile sayıldı) | K22: kanal yapılandırması F4'te `speaker_zones`'a taşınır | F4'te ayrı bir alt adımda (4a'nın ilki) kanal satırı fikstürüyle yeniden yazılır; sınanan **davranış** (hangi çıkış çalar, "kapalı" iken ne yazar, bölüm seçimi) aynen korunur, yalnız kurulum biçimi değişir |
| `tests/test_komuta_uyari_ve_anons.py:405-456` (`_ihlali_kaydet` doğrudan; `_AnonsCasusu.duyur` tam 4 konumsal argüman) | Yeni bilgi `duyur`'a argüman olarak geçerse casus `TypeError` verir | İmzalar korunur, yeni bilgi yalnız `olay=None` anahtar kelimesiyle; casus `**kw` kabul edecek biçimde güncellenir |
| `tests/test_ayarlar.py` (iki yönlü eşitlik) | Yeni ve emekli `.env` anahtarları | Her fazda anahtar listesiyle birlikte güncellenir |
| `tests/test_bolge_cizim_kolayligi.py:183`, `:195` | JS renk eşlemesi (`kamera_detay.js:48-53`) ve `stil.css` `--bolge-*` sayısı `BOLGE_TIPLERI` ile eşit olmalı | İki yeni renk değişkeni `stil.css`'e (`:94-99` yanına), iki eşleme `kamera_detay.js`'e eklenir; test değişmez |
| `tests/test_ses_cikisi.py:88-93` (`komut[0] == "powershell"`) | Windows çalma yolu `winsound` olur | Test "Windows'ta alt süreç açılmaz, `winsound.PlaySound` çağrılır" olarak yeniden yazılır |
| `tests/test_ses_cikisi.py:160` (`cihaz_bagli_mi("") is True`) | R37: boş seçimde varsayılan çıkış gerçekten denetlenir; liste okunamazsa `None` | Beklenen değer `None` olur (Faz 4) |
| `tests/test_veritabani.py:13` (`BEKLENEN_TABLOLAR`) | Yeni tablolar (`test_veritabani.py:39-42` bu kümeyle karşılaştırır) | Her göçle güncellenir |
| `tests/rules/test_kkd.py:86` | Kalem başına olay | `details.eksik_kkd` tek elemanlı liste olarak korunur; test değişmez |

`HAZIR_KURALLAR` sözlük olarak kalır (`test_hazir_kurallar.py:91` bozulmaz); ikinci hazır
kurallar ayrı `EK_HAZIR_KURALLAR` sözlüğündedir. Yasak alan hazır kuralı 2 sn'de kalır
(`:109-112` bozulmaz).

---

## 5. KKD üç durumlu karar ve veri döngüsü (model seçimi: mevcut iki aşamalı plan; unknown koşulları; sürücü muafiyeti; gölge mod; ölçüm)

### 5.1 Bugün

- **Karar tarafı hazır ve testli:** üç durum (`tipler.py:17-19`); "belirsiz asla olay değildir"
  (`kkd.py:128-129`, `tests/rules/test_kkd.py`); iz bazlı pencere (`kkd.py:57-60`); boy
  eşikleri 120/80 px ve kesik kutu (`kkd.py:105-117`, `:170-178`); düşük güven belirsiz
  (`:115-116`); olaya model sürümü (`:163`); kırpma sözleşmesi (`kkd_siniflandirici.py:20-21`,
  üstten %10, 128×256).
- **Model yok:** `KkdSiniflandirici(None)` (`supervizor.py:90`) gözlem üretmez; model verilse
  `NotImplementedError` (`kkd_siniflandirici.py:56-59`). Sonuç: sahada PPE olayı hiç çıkmaz
  (olgu 7). KKD kuralı ayrıca bölgesiz çalışmaz (`kkd.py:36-38`).
- **Veri toplama ön koşulsuz açık:** KKD bölgesindeki kişiden saatte en çok
  `KKD_ORNEK_SAAT_LIMIT` (60) kırpık (`supervizor.py:582-638`); piksel eşiği ve Rev.02 kapısı
  yok. Anahtarın alt sınırı 1'dir (`ayarlar.py:278`), yani bugün toplamayı kapatmanın yolu yok.

### 5.2 Model seçimi: iki aşamalı (docs/04 §2 korunur)

Kişi kutusu kırpılır, küçük bir sınıflandırıcıya verilir. Tek aşamalı (baret/yelek dedektörü +
IoU ile kişiye bağlama) belgeli alternatif olarak kalır ama seçilmedi:

- Kırpığa üç düğmeyle etiketleme ucuzdur ve etiketleme sayfası zaten var (`kkd_web.py`).
- "Görünmüyor" çıkışı iki aşamalıda doğrudan var.
- Tespit modeline ve sınıf listesine dokunulmaz.

**Model:** MobileNetV3-Small sınıfı küçük bir CNN (docs/04 §6.1). Çıkış iki baş: baret
{var, yok, görünmüyor}, yelek {var, yok, görünmüyor}, her biri softmax. "Görünmüyor" ya da en
yüksek olasılık `min_confidence` (0,70, `parametreler.py:47`) altındaysa gözlem **belirsiz**.
Eğitim ürün dışında yapılır (§5.8). Ürüne yalnız `.onnx` girer; çıkarım zaten kurulu ORT ile.
Karedeki kişiler toplu verilir.

**Hız:** ölçülmedi. `yolox_tiny` CPU'da bütçenin %100'ünde (AUDIT-OLCUM §1.2).
`tests/hiz_kiyas`'a sınıflandırıcı turu eklenir; bütçe aşılırsa önce `KKD_KARE_ARALIGI`
büyütülür, sonra GPU gerekir. Bütçe aşımı `ANALYSIS_DEGRADED` ile görünür olur.

### 5.3 "Belirsiz" koşulları

| §4.3 koşulu | Nerede | Durum |
|---|---|---|
| Baş / gövde görünmüyor | modelin "görünmüyor" çıkışı | F3 |
| Kutu kare kenarında kesik | `kkd.py:170-178` (`require_full_bbox`) | var |
| Kutu yüksekliği eşiğin altında | `kkd.py:105-111`, baret 120 / yelek 80 px | var; §4.3'ün 60 px'i uygulanmaz (Ç13) |
| Bulanıklık | analiz katmanında kırpığın Laplacian varyansı → `KkdGozlem.netlik`; `rules/kkd.py` `min_netlik` altını belirsiz sayar | F3; eşiğin **tek yeri** kural parametresi `min_netlik` (varsayılan None = kapalı; `.env` anahtarı açılmaz, K2). DALSAN kırpıklarında ölçülene kadar sayı yazılmaz. OpenCV gerektiği için hesap `analiz/`'de, karar `rules/`'da |
| Başka kişiyle örtüşme | iki kişi kutusu IoU > `max_kisi_ortusmesi` → belirsiz (docs/04 §8.3 "iki kişi üst üste") | F3; `KkdParams.max_kisi_ortusmesi`, varsayılan None = kapalı (`tests/rules/test_kkd.py` değişmez); değer gölge ölçümüyle |
| Düşük güven | `kkd.py:115-116` | var |
| Araç içindeki kişi | §5.4 | F3 |

Her yeni kaynak için "belirsiz asla olay üretmez" testi eklenir; ayrıca açık bir olay sürerken
karar belirsize dönerse olayın kapandığını (süresinin ihlal olarak uzamadığını) sınayan test
(§6.3).

### 5.4 Sürücü muafiyeti

- `KkdParams.surucu_muaf` (varsayılan **açık**, docs/04 §5.3 #4–5 cevaplanana kadar yanlış alarmı
  önler; S3).
- Kişi kutusunun ayak noktası bir araç (`forklift`, `truck`) kutusunun içindeyse **ya da**
  kişi kutusunun alanının `surucu_ortusme_orani` kadarı (öneri 0,6) araç kutusuyla örtüşüyorsa o
  karede baret ve yelek gözlemi **belirsiz** yazılır. Hesap saf geometridir.
- **Sınır:** forklift sınıfı henüz yok; bugün yalnız model "truck" dediği araçta çalışır. Bu
  yanlış alarm yönünde bir açıktır ve gölge modda ölçülür.

### 5.5 Kapsam ve `ppe_exempt`

- **Varsayılan (`kapsam=bolge`):** bugünkü dahil etme modeli. Kural yalnız çizilen
  `ppe_required` bölgesinde çalışır (docs/04:44, docs/08 R9). v2'de bu bölgenin içindeki
  `ppe_exempt` poligonları oyulur (kabin, ofis köşesi).
  Oyma **iki yerde** uygulanır: kural kararı (`rules/kkd.py`) ve kırpığı üreten kapı
  `boru_hatti.kkd_bolgesinde_mi` (`:276-282`); ikincisi hem sınıflandırıcıyı (`:302`) hem veri
  örneklemeyi (`supervizor.py:591`) kapılar. Yalnız kurala uygulansa muaf alandan (kabin, ofis
  köşesi) kırpık toplanmaya devam ederdi (KVKK).
- **Seçenek (`kapsam=muaf_disi`, yalnız S3 bunu seçerse kodlanır):** §4.3'ün dışlama modeli.
  Kural bölgesiz çalışır, `ppe_exempt` içindekileri atlar. Bugün KKD kuralı üç katmanda bölgeye
  kilitli: form/doğrulama (`ortak.py:35` `BOLGE_ZORUNLU_KURALLAR`, `kurallar.py:129`),
  değerlendirici (`kkd.py:36-38`) ve boru hattı (`kkd_bolgesinde_mi`); üçü de değişir. Kırpık
  sayısı, CPU yükü ve işlenen kişisel veri artar (ölçülecek). Hangisinin kullanılacağı politika
  sorusudur (S3); cevap gelmezse bu kip yazılmaz, docs/07'ye satır olur.

### 5.6 Zamansal pencere ve olaylar

- **Pencere değişmez:** 15 değerlendirme, en az 8 geçerli gözlem, oran 0,75, kalış 3 sn
  (`parametreler.py:48-51`). Aritmetik: KKD her 5. karede çalışır (`boru_hatti.py:49`), 6 fps'te
  saniyede 1,2 gözlem eder. 15 değerlendirme ≈ 12,5 sn; 8 geçerli gözlem ≈ 6,7 sn.
- **§4.5 "son 2 sn, ≥%70":** 2 sn'de ~2,4 gözlem düşer, en az 8 gerekir; bugünkü kadansla
  **sağlanamaz.** Sağlamak için kadans 1 (sınıflandırıcı yükü ~5 kat) ve en az gözlem eşiğinin
  düşürülmesi gerekir. docs/04 §7.2 ve E10 gereği muhafazakâr pencere varsayılandır (S16).
- **Kalem başına olay:** `PPE_NO_HELMET` (high) ve `PPE_NO_VEST` (medium) ayrı `Ihlal`; cooldown
  anahtarına kalem eklenir (`kkd.py:146`). `details.eksik_kkd` tek elemanlı liste olarak kalır
  (`ortak.py:249-254` özeti ve `test_kkd.py:86` bozulmaz). İkisi aynı anda düşerse dağıtıcı iki
  kısa WAV'ı art arda çalar.
- **Kapanış:** oy "var"a dönünce, karar `bitis_s` boyunca **belirsiz** kalınca (geçerli gözlem
  `min_valid_observations` altına düştü: kişi uzaklaştı, sırtını döndü, kutu kesildi), kişi
  bölgeden çıkınca ya da iz kaybolunca (§6.3). Belirsiz kanıtla "ihlal sürüyor" denmez.

### 5.7 Gölge mod ve devreye alma kapısı

1. KKD hazır kuralı (`ortak.py:399`) `shadow_mode=1` ile doğar (docs/04 §8.2; docs/09
   "değişmeyen kararlar"). Bugün KKD olay üretmediği için bu mevcut bir davranışı değiştirmez.
   Olay yazılır; anons ve ekran bandı çıkmaz (`supervizor.py:555-557`, `uyari.js:108`).
2. En az 3 gün her KKD olayı "İncelendi" ya da "Yanlış alarm" diye işaretlenir
   (`olaylar_web.py:198`).
3. **Kapı** (`golge_modu_degistir`, `komuta.py:207`), kalem ve model sürümü başına; üç şartın
   üçü de sağlanmalı:
   - precision = incelenmiş doğru / (doğru + yanlış) ≥ `KKD_KAPI_PRECISION` (0,90);
   - kapı döneminde (en az `KKD_KAPI_GUN` = 3 gün) o kalem ve model sürümünün **incelenmemiş
     olayı kalmamış** (docs/04 §8.2 "üretilen tüm KKD olayları incelenir"); yoksa yalnız
     incelenenlerden hesaplanan oran seçici inceleme yüzünden şişebilir;
   - incelenmiş olay sayısı ≥ `KKD_KAPI_EN_AZ_OLAY` (öneri 30: hiç yanlış alarm yokken bile
     n olayla %95 güvenle söylenebilecek en iyi şey "hata oranı ≤ 3/n"dir, "üçler kuralı";
     n = 30 bunu %10'a, yani 0,90 eşiğine indirir; S33).
   Karnede precision'ın yanında N ve inceleme kapsamı % gösterilir. Kapı geçilmeden anons yalnız
   açık bir onayla açılabilir ("ölçülmeden açıyorum"); onay sistem olayı olarak yazılır.
   **Uygulandı (F3e-1, `web/kkd_karnesi.py`):** gün şartı o kalem ve sürümün ilk olayından bu
   yana geçen süredir (model yüklenme anı kalıcı kaydedilmiyor; ilk olay onun alt sınırı).
   Sayaç yalnız `details.ppe.model_version`'ı yüklü sürüme eşit olayları sayar; model yüklü
   değilse kapı kapalıdır. Kuralın `required_ppe` kalemlerinin hepsi geçmelidir. Kapı
   `golge_modu_degistir`'de sunucuda denetlenir (gri düğme yalnız önceden söyler); onay
   `PPE_GATE_OVERRIDDEN` yazar ve yüklü sürümü yine onaylar, yoksa süpervizör kuralı hemen
   gölgeye geri alırdı. Precision kesirle karşılaştırılır (27/30 = 0,90 geçer), ekranda
   aşağı yuvarlanır.
4. **Model sürümü değişince gölgeye dönüş:** kapı geçildiğinde onaylanan sürüm
   `rules.approved_model_version`'a yazılır (008, yalnız ADD COLUMN). `params`'a konmaz, çünkü
   params kural imzasına girer (`motor.py:76-86`) ve cooldown ile pencereleri sıfırlardı.
   Süpervizör yapılandırmayı yüklerken yüklü KKD modelinin `model_surumu`'nu (`kkd.py:163`
   deseni) bu sütunla karşılaştırır; farklıysa ve kural gölgede değilse `shadow_mode=1` yazar
   ve `PPE_MODEL_CHANGED` sistem olayı üretir. Bugün `golge_modu_degistir` (`komuta.py:207-208`)
   yalnız `shadow_mode` yazıyor; kapıdan geçişte sürümü de yazar.
5. Recall **ölçülür ama taahhüt edilmez** (docs/04 §8.1, E10).

### 5.8 Veri döngüsü

- **Kapı (F2):** SQLite `ppe_collection_gate` (007, tek satır: `enabled`, `changed_at`, `note`).
  `.env`'de **değil**: `.env` restart ister (`ayarlar.py:39` `frozen=True`, `ayar_rotalari.py:18`)
  ve Docker'da salt okunurdu (R27); `.env`'de dursaydı operatör toplamayı "kapattığında"
  yeniden başlatmaya kadar kırpık toplanmaya devam ederdi (KVKK açığı). Açmak için `/kkd`
  sayfasında "Rev.02 ek protokolü imzalandı, çalışan aydınlatması yapıldı" onayı istenir;
  açılış ve kapanış `PPE_COLLECTION_CHANGED` sistem olayı (Faz 5'ten sonra ayrıca
  `access_log`) olarak kaydedilir. `_kkd_ornekle` (`supervizor.py:582`) örnek yazmadan hemen önce
  satırı okur (saatte en çok `KKD_ORNEK_SAAT_LIMIT` kez, ucuz); kapatma **gecikmesizdir**.
  Önerilen başlangıç değeri `kapali`; mevcut kurulumda toplama durur, bu yüzden operatöre soruldu
  (S10).
- **Örnek sınırı:** yalnız KKD kuralının `min_person_height_px`'i (varsayılan 120) üstündeki
  kişiden örnek alınır (daha küçüğü eğitimde işe yaramaz); sayı ikinci kez yazılmaz, kural
  parametresinden türetilir. Örnekle birlikte kişi boyu ve netlik kaydedilir (008).
- **Kaynaklar:** otomatik örnekleme; planlı çekim seansı (docs/04 §4.2, İSG refakatinde, olumsuz
  örnekler dahil); yanlış alarm geri beslemesi.
- **Politika ve etiketleme:** önce `docs/kkd-politika.md` (docs/04 §5.3'teki 10 sorunun
  DALSAN İSG cevapları). Zor negatifler docs/04 §5'e eklenir: beyaz saç, şapka, bone ile beyaz
  baret; reflektörlü mont ile yelek; gece yansıması; sırt çantası; yağmurluk; kabin içi sürücü.
  `ppe_samples.hard_case` ile işaretlenir. Etiketleme mevcut üç düğmeyle.
- **Bölme:** kamera + yerel gün grupları; rastgele bölme yasak (docs/04 §5.4).
  `egitim/veri_seti.py` bunu zorlar; bir test "aynı kamera ve gün iki kümede olamaz" der.
- **Dışa aktarım:** stdlib `zipfile`; kırpıklar + etiket CSV'si + bölme + sha256 manifest.
- **Eğitim (ürün dışı, Ç37):** ayrı venv, PyTorch, GPU'lu makine; operatör dışı, uzman işi,
  tek seferlik (S11, S31). Adımları docs/04 §6'ya runbook olarak yazılır; CLAUDE.md §5'teki
  `egitim/` açıklaması "veri seti, değerlendirme, HTML rapor; eğitim ürün dışı" olur. Ürün içi
  kısım docs/09 #7'yi korur: veri seti dışa aktarımı ve değerlendirme **tek komutla HTML
  rapor** üretir (§5.9). Artırmalar docs/04 §6.2'den (toz/sis, düşük ışık, bulanıklık, parlama,
  ölçek) + yağmur (Ç46). Ön eğitimli ağırlığın lisansı **DOĞRULANMADI** (S20). Çıktı yalnız
  `.onnx`.
- **Model kartı:** ONNX `custom_metadata_map` içinde: başlar, veri penceresi (tarih aralığı,
  kamera listesi), test metrikleri, eğitim tarihi. `model_surumu` = dosya adı + sha256'nın ilk 12
  karakteri; her KKD olayına `details.ppe.model_version` olarak zaten yazılıyor (`kkd.py:163`).

### 5.9 Ölçüm

- `egitim/degerlendirme.py` test bölümünde ORT ile koşar ve **tek HTML rapor** üretir: kalem başına
  var/yok/görünmüyor karışıklık tablosu, "yok" için precision ve recall, belirsiz oranı, en kötü
  50 örneğin ızgarası, kamera/gün/zor örnek kırılımı (docs/09 #7). Operatör sayı okumak yerine
  bakarak karar verir.
- Saha precision'ı gölge moddaki inceleme işaretlerinden (§5.7). Rapor sayfasına olay kodu
  başına "yanlış alarm oranı" kırılımı eklenir; yanında inceleme kapsamı %.
- KKD uyum oranı (vardiya/gün/hafta) bu turda yok; S34 "evet" ise Ç40'taki biçimle eklenir.
- Ölçülmeyen hiçbir KKD metriği belgeye ya da ekrana yazılmaz; yerinde "ölçülecek" yazar.

### 5.10 Operatörün göreceği

- Kamera önizlemesinde kişi kutusu yeşil (uyumlu), kırmızı (eksik) ya da gri (belirsiz).
- Olay listesinde "Baret yok — Yüksek — gölge" satırları.
- Model dosyası yoksa KKD sayfası "Model yüklü değil: KKD kuralı olay üretmez" der; varsa model
  adı ve sürümü görünür.
- KKD sayfasının üstünde "Veri toplama: KAPALI — Rev.02 onayı bekleniyor" ya da "AÇIK" satırı;
  kutu işaretlenince yeniden başlatma gerekmez.

---

## 6. Kural motoru ve olay sözlüğü (tablo: v2 adı · mevcut karşılık · durum · not; eşiklerin saklandığı yer; durum makinesi/histerezis kararı; kalibrasyonsuz mesafe davranışı)

### 6.1 Olay sözlüğü

Durum: `exists` (var, yalnız kod verilir) · `rename` (var, adı ve önemi v2'ye bağlanır) ·
`new` (yeni) · `deferred` (ertelendi).

| v2 adı | Mevcut karşılık | Durum | Not |
|---|---|---|---|
| `PPE_NO_HELMET` | `ppe_violation`, `details.eksik_kkd` içinde `helmet` (`kkd.py:119-168`) | rename + bölünme | high. Model gelene kadar hiç üretilmez. Pencere docs/04 (§5.6). Gölge modda doğar |
| `PPE_NO_VEST` | aynı, `vest` | rename + bölünme | medium. Yelek eşiği 80 px |
| `PERSON_IN_VEHICLE_LANE` | `zone_intrusion` inside, person, `vehicle_area`; hazır kuralı yok (`vehicle_area` hazır kuralı `safe_distance` kurar, `ortak.py:385-397`) | rename + yeni ek hazır kural | medium; aynı bölgede ayak noktası içeride bir araç varsa high. `min_dwell_s` 1,5 (§4.5). Geçitte ihlal yok. Gölge modda doğar |
| `VEHICLE_ON_WALKWAY` | `zone_intrusion` inside, [forklift, truck], `pedestrian_path`; elle kurulabilir | rename + yeni ek hazır kural | high; `min_dwell_s` 1,0 (§4.5); geçitte ihlal yok; gölge modda doğar. Bugün "truck" binek aracı da içerdiği için binek araç da tetikler (bilinen sınır) |
| `VEHICLE_PERSON_PROXIMITY` | `safe_distance` (`mesafe.py`) | rename | critical; `distance_m` 3; hareketli araç şartı var (`:58-61`). Yeni: `histerezis_m`, R21 (pasif bölge `:34`). Kalibrasyonsuz pasif (§6.4) |
| `RESTRICTED_ENTRY` | `zone_intrusion` inside, person, `restricted`; hazır kural `ortak.py:346-357` | rename | high. `min_dwell_s` **2 sn kalır** (şema varsayılanı); §4.5'in 1 sn'si gölge ölçümüne bağlı (S25) |
| `PERSON_OFF_WALKWAY` | `zone_intrusion` outside, person, `pedestrian_path`; hazır kural `ortak.py:332-344` | rename | medium. §4.5'te yok, mevcut özellik bozulmaz. Yolun dışındaki her yeri tetikleyebilir; yanlış alarm riski yüksek, gölge ölçümü önerilir |
| `PERSON_IN_LOADING_AREA` | inside, person, `loading_area` (`ortak.py:359-370`) | rename | medium |
| `VEHICLE_OUT_OF_POSITION` | outside, truck, `truck_parking` (`ortak.py:372-383`) | rename | low |
| `VEHICLE_OVERSPEED` | `vehicle_speed` (`hiz.py`, `sema/005`) | rename | high; kalibrasyon şart (`motor.py:36`) |
| `ZONE_INTRUSION` | sözlüğe uymayan `zone_intrusion` birleşimi | new (yedek kod) | önem kural satırından; bölge tipi `details`'te |
| `CAMERA_DOWN` | sistem olayı "Kamera çevrimdışı" (`supervizor.py:662-669`); eşik `kamera.py:50` (60 sn) | rename | system. Kamera bir kez çevrimiçi olduktan sonra 10 sn; ilk bağlantıda 60 sn tolerans. `resolved_at`, UP gelince yazılır |
| `CAMERA_UP` | "Kamera tekrar çevrimiçi" (`supervizor.py:670-672`) | rename | system; 5 sn kesintisiz kare şartı; anlık (`resolved_at = occurred_at`) |
| `VIDEO_FINISHED` | "Video analizi tamamlandı" (`supervizor.py:656-661`) | rename | system, anlık; yalnız tek geçişlik video |
| `DISK_LOW` | "Disk azalıyor" (`supervizor.py:748-753`) | rename | system. Faz 5: `DISK_DUR_GB` altında kanıt fotoğrafı yazımı durur, olay kaydı sürer |
| `MODEL_LOAD_FAILED` | "Tespit modeli yüklenemedi" (`supervizor.py:292`, tipli hata yolu). Genel istisna yolu (`:222-233`) bugün olay yazmıyor | rename + genişletme | system. İki yol da bu kodu yazar. KKD modeli ve sha256 uyuşmazlığı da bu kod. Veritabanı açılamazsa (`:209-220`) olay yazılamaz; yalnız günlük + `/saglik` sorunu |
| `INFERENCE_DEVICE_FALLBACK` | `cihaz_uyarisi` sistem olayı (`supervizor.py:274-277`) | rename | system; CUDA istenip CPU'ya düşülünce |
| `ANALYSIS_STALLED` | yok (bekçi yok, R5) | new | system; `bekci.py` (§3.6) |
| `ANALYSIS_DEGRADED` | yok (kare işleme hatası yalnız günlükte, `supervizor.py:529-532`) | new | system; işlenen fps `FPS_UYARI_ORANI` (mevcut, 0,6) × hedefin altında `ANALIZ_YAVAS_SURE_SN` (öneri 60) kalırsa ya da kamera hattı ardışık hata sayısı `ANALIZ_HATA_ESIGI`'ni (öneri 30) aşarsa |
| `SYSTEM_STARTED` / `SYSTEM_STOPPED` | yalnız günlükte "Sistem hazır" / "durduruluyor" (`uygulama.py` lifespan) | new | system; uptime ölçümünün kanıtı (§14) |
| `PPE_COLLECTION_CHANGED` | yok | new | system; KKD veri toplama açıldı/kapandı |
| `PPE_MODEL_CHANGED` | yok | new (F3) | system; KKD modeli sürümü onaylı sürümden farklı, kural gölgeye döndürüldü (§5.7) |
| `PPE_GATE_OVERRIDDEN` | yok | new (F3e) | system; KKD anonsu kapının şartları sağlanmadan "ölçülmeden açıyorum" onayıyla açıldı; ayrıntıda kural id'leri, model sürümü ve eksik şartlar (§5.7) |
| `AUDIO_CHANNEL_DOWN` | yok (`cihaz_bagli_mi` yalnız `/anons` render edilirken, `anons_web.py:81`) | new (F4) | system; 30 sn kesintisiz "koptu" |
| `AUDIO_CHANNEL_UP` | yok | new (F4) | system; 2 ardışık "bağlı"; açık DOWN'u kapatır |
| `ALERT_UNDELIVERED` | yok (başarısız anons yalnız `son_sonuc` metninde, `anons.py:360-366`) | new (F4) | system; aynı kamera için en çok `ULASMAYAN_UYARI_ARALIGI_SN`'de (öneri 300) bir kez; aradaki ulaşmayanlar sayılıp olay `details`'ine yazılır |
| (007 öncesi olaylar) | `event_code` NULL | exists | geriye dönük kod yazılmaz; ekran kural tipi adını kullanır (`ortak.py:239`); 007 bunlara `resolved_at = occurred_at` yazar |
| düşme, ek KKD sınıfları, mesajlaşma/ışıklı kule kanalları | docs/07 #13, #8, #4 | deferred | §4'te v1 kapsamında değil |

Sistem olayları fabrika hoparlöründen anons edilmez (çalışanın yapabileceği bir şey yok); ekran,
sistem şeridi, günlük ve (F4, S4 "evet" ise) webhook'a gider.

**§4.5 olay alanları → v2 karşılığı:**

| §4.5 alanı | v2'de | Durum |
|---|---|---|
| `event_id` | `events.id` | var |
| `camera_id` | `events.camera_id` | var |
| `track_id` | `details.takip_idler` (`yazici.py:50-54`); mesafede iki iz | var (details'te) |
| `type` | `events.event_code` (007); 007 öncesi olayda kural tipi | yeni |
| `severity` | `events.severity` (007) | yeni |
| `confidence` | `details.guven`: tespit güveni ortalaması; KKD'de karar penceresindeki sınıflandırıcı güveni ortalaması. **Modelin skorudur, ölçülmüş doğruluk değildir**; ekranda "model güveni" diye yazılır | yeni (F2, KKD kısmı F3) |
| `zone` | `events.rule_snapshot` içindeki `zone_id` (kural satırının anlık görüntüsü, `yazici.py:51`; bölgenin adı/poligonu değil) | var (kimlik olarak) |
| `started_at` | `events.occurred_at` | var |
| `resolved_at` | `events.resolved_at` (007) | yeni |
| `snapshot_path` | `events.snapshot_path` | var |
| `clip_path` | yok | ertelendi (Ç18, S5) |

### 6.2 Eşiklerin saklandığı yer

- **Kural başına:** SQLite `rules.params` JSON, şeması ve varsayılanları tek kaynaktan
  (`rules/parametreler.py`, Pydantic); ayrıca `rules.cooldown_s`, `rules.severity`,
  `rules.shadow_mode`. Yeni alanlar: `bitis_s` (ortak), `gecit_haric` (bölge), `histerezis_m`
  (mesafe), F3'te KKD alanları. Varsayılanlar bugünkü davranışı korur. Kural formu varsayılanları
  şemadan türetir (R25).
- **Olay kodu ve varsayılan önem:** `rules/olay_kodu.py`. Kural satırındaki `severity`
  `'warning'` (bugünkü tüm satırlar) ise kodun varsayılanı kullanılır; başka değerse o geçerlidir.
- **Süreç düzeyi:** `.env` (§3.7).
- **Hâlâ kodda duran sabitler** (AUDIT §7.2; ayrım kuralı Ç36, operatör onayı S36). Önceki
  sürümdeki "davranışı etkileyen üçü taşınır, kalanlar JPEG/HSV/bakım" cümlesi eksikti; tam
  liste:

| Sabit (dosya:satır) | Karar | Gerekçe |
|---|---|---|
| Kopukluk eşiği (`kamera.py:50`, 60) | `.env KAMERA_KOPUK_ESIGI_SN` (10) | CAMERA_DOWN üretir |
| İlk bağlantı toleransı (aynı sabitten ayrılır, 60) | belgelenmiş sabit `ILK_BAGLANTI_TOLERANSI_SN` | Yalnız hiç bağlanmamış kameranın ilk dakikası; ekranda "bağlanıyor" görünür |
| CAMERA_UP kararlılığı (yeni, 5 sn) | `.env KAMERA_UP_KARARLILIK_SN` | UP olayı ve olay seli (S18) |
| KKD kare aralığı (`boru_hatti.py:49`, 5) | `.env KKD_KARE_ARALIGI` | KKD kararının hızı ve CPU |
| Kayıp toleransı (`bolge_ihlali.py:20`, `hiz.py:41`, `sayim.py:40`, 5) | süpervizör `TAKIP_HAFIZA_SN`'den türetip geçirir (§6.3) | Kalış sayacı |
| Kamera formu örnekleme hızı (`kameralar.py:98` `Form(6)`) | `.env KARE_ORNEKLEME_FPS` okunur (bugün okunmuyor) | Hata düzeltmesi |
| `ANALYSIS_DEGRADED` süresi ve hata sayısı (yeni) | `.env ANALIZ_YAVAS_SURE_SN`, `ANALIZ_HATA_ESIGI` | Olay üretir |
| `ALERT_UNDELIVERED` hız sınırı (yeni) | `.env ULASMAYAN_UYARI_ARALIGI_SN` | Olay üretir |
| KKD kapısı precision / gün / en az olay (yeni) | `.env KKD_KAPI_*` | Anonsun açılmasını belirler |
| KKD örnek piksel sınırı (yeni) | kural parametresi `min_person_height_px`'ten türetilir | Sayının ikinci yeri olmaz |
| Kişi örtüşmesi (yeni) | kural parametresi `max_kisi_ortusmesi` (None = kapalı) | KKD kararı |
| AUDIO_CHANNEL_UP için 2 ardışık yoklama (yeni) | belgelenmiş sabit | Histerezisin en küçük anlamlı biçimi; süre `ANONS_SAGLIK_ARALIGI_SN` ile ayarlanır |
| IP hoparlör TCP yoklaması 3 sn (yeni) | belgelenmiş sabit (`kamera.py:52` `_AG_KONTROL_SN` deseni) | Zaman aşımı, karar eşiği değil |
| Kesik kutu payı (`rules/kkd.py:25`, 2 px) | belgelenmiş sabit | Geometrik tolerans; kutu kenara 2 px'ten yakınsa "kesik" |
| NMS skor çarpanı (`tespit.py:266`, × 0,9) | belgelenmiş sabit | `TESPIT_*` eşiklerinin iç ayrıntısı |
| Hız `dt` aralığı (`motor.py:39-40`, 0,05 / 5 sn) | belgelenmiş sabit | Sayısal kararlılık sınırı |
| Zaman aşımları (`anons.py:143`, `:210`; `ses_cihazlari.py:49`), yeniden bağlanma (`kamera.py:47-48`), bakım/damga aralıkları (`supervizor.py:48-50`), JPEG kalitesi, HSV bantları (`alan_bulucu.py:45-85`), `busy_timeout`, günlük dönüşü | belgelenmiş sabit | İç mekanik |

### 6.3 Durum makinesi ve histerezis kararı

**Seçilen yol (ŞARTNAME aşısı):** cooldown değerlendiricilerde kalır; `degerlendir()` bugünkü
gibi `list[Ihlal]` döndürür. Böylece `tests/rules`'taki 85 test dokunulmadan kalır
(değerlendirici testleri zaten `KuralMotoru.degerlendir` üzerinden sınıyor, ör.
`tests/rules/test_bolge_ihlali.py`, `test_kkd.py`; `test_saflik.py` AST bekçisi yeni dosyaları da
kapsar). Üstüne iki şey eklenir:

```python
# rules/ içinde, saf — imza taslağı
class Degerlendirici(Protocol):
    def degerlendir(self, baglam) -> list[Ihlal]: ...  # değişmez
    def aktif_anahtarlar(
        self, baglam
    ) -> set[tuple]: ...  # yeni: ÇIKIŞ eşiğiyle hâlâ süren koşullar


class OlayDurumMakinesi:  # rules/olay_durumu.py
    def guncelle(
        self,
        zaman_s: float,
        ihlaller: list[Ihlal],
        aktifler: set[tuple],
        kurallar: dict[int, Kural],
    ) -> list[OlayGecisi]: ...


@dataclass
class OlayGecisi:
    asama: str  # "acildi" | "hatirlatma" | "kapandi"
    anahtar: tuple  # Cooldown anahtarıyla aynı biçim: (kural, kamera, iz[, iz2][, kalem])
    ihlal: Ihlal | None
    sebep: str = ""  # kapandi: kosul_bitti | belirsiz | iz_kayboldu | kural_degisti | kapanis | yeniden_baslama
```

- **Açılış:** değerlendiricinin ürettiği `Ihlal` için anahtar açık değilse `acildi` → yeni olay
  satırı.
- **Hatırlatma:** anahtar zaten açıkken değerlendirici cooldown dolduğu için yeniden `Ihlal`
  üretirse `hatirlatma` → **yeni satır açılmaz**, yalnız ses kanallarına tekrar anons (S17).
  Bugün uzun ihlalde her `cooldown_s`'de yeni olay satırı açılıyor (`cooldown.py:16-22`); olay
  listesi artık dolmaz, duyulur davranış korunur.
- **Kapanış (zamansal histerezis):** anahtar `aktif_anahtarlar()` içinde `bitis_s` boyunca
  görünmezse `kapandi` → `UPDATE events SET resolved_at`. Kapanıştan sonra aynı anahtar,
  değerlendiricinin cooldown'u dolmadan yeniden açılamaz (cooldown zaten orada).
- **Giriş ≠ çıkış eşiği:**

| Kural | Giriş | Çıkış (aktif sayılmayı bırakma) |
|---|---|---|
| Bölge | ayak noktası bölgede ve kalış ≥ `min_dwell_s` | ayak noktası `bitis_s` boyunca bölge dışında ya da iz kayıp toleransını aştı |
| Mesafe | mesafe < `distance_m`, `min_frames` ardışık | mesafe > `distance_m + histerezis_m` ya da çift kayboldu |
| KKD | geçerli gözlemlerde "yok" oranı ≥ `violation_ratio` | oy "var"a döndü; **karar `bitis_s` boyunca belirsiz** (geçerli gözlem < `min_valid_observations`, `kkd.py:125-129`; sebep `belirsiz`); kişi bölgeden çıktı ya da iz kayboldu. Belirsiz dönem olay süresine ihlal olarak eklenmez, hatırlatma üretmez |
| Hız | pencere ortancası > `speed_limit_mps` | ortanca sınırın altında `bitis_s` boyunca |

- **Açılış ve kapanışta asılı olaylar:** süpervizör açılışta `resolved_at IS NULL` olan ihlal
  satırlarını `yeniden_baslama` sebebiyle kapatır; düzgün kapanışta (`supervizor.durdur`) açık
  olayları `kapanis` sebebiyle kapatır. Kapanış sebebi `details`'e yazılır.
- **Kayıp toleransı:** bugün sayı olarak 5 değerlendirme (`bolge_ihlali.py:20`, `hiz.py:41`;
  6 fps'te ≈ 0,83 sn). Takip hafızası 2 sn'ye çıkınca kural da iz'i o kadar beklemeli, yoksa
  kalış sayacı yine sıfırlanır. Değerlendiriciler toleransı kurucu parametresi olarak alır; motor
  bunu `ceil(TAKIP_HAFIZA_SN × fps)` olarak verir; verilmezse bugünkü 5 kalır (testler değişmez).
  `rules/` `.env` okumaz; değeri süpervizör geçirir.
- **Geçit istisnası:** bölge ihlalinde ayak noktası aynı kameradaki etkin bir `crossing`
  poligonundaysa koşul sağlanmış sayılmaz (`gecit_haric`, varsayılan açık). Geçit poligonları
  mevcut `baglam.bolgeler` (`dict[int, Bolge]`, `motor.py` `Baglam`) içinden
  `b.tip == "crossing"` ile seçilir; süpervizör kameranın bütün bölgelerini tipleriyle zaten
  yüklüyor (`supervizor.py:453-469`). **`Baglam` değişmez**, değerlendirici çağrı biçimi korunur.
- **Bağlamsal önem:** `PERSON_IN_VEHICLE_LANE` için aynı karede aynı bölgede bir aracın ayak
  noktası varsa `siddet=high`.

### 6.4 Kalibrasyonsuz mesafe davranışı

- Kalibrasyon yoksa `safe_distance` ve `vehicle_speed` **pasif** kalır (`motor.py:36`
  `KALIBRASYON_GEREKTIREN`; `mesafe.py:25-26`); arayüz "kalibrasyon bekleniyor" der. §4.5'in
  piksel sezgisi + `confidence: low` yolu uygulanmaz (Ç15). S7 "kalibrasyon yapılamaz" diye
  cevaplanırsa bile sezgi yalnız gölge modda, anons edilmeden ve metre yazılmadan ölçüm için
  açılabilir; bu ayrı bir karardır.
- **Görünürlük:** etkin bir `safe_distance` ya da `vehicle_speed` kuralı kalibrasyon yüzünden
  pasifse bu, yalnız kural sayfasındaki rozetle kalmaz: `/saglik` `sorunlar`'a
  `kritik_kural_pasif`, kurulum listesine (`kilavuz.py:339` `kurulum_durumu`) kırmızı madde
  eklenir (bugün `kilavuz.py`'de kalibrasyon maddesi yok).
- **Doğrulanmamış kalibrasyon:** kontrol ölçümü yoksa mesafe olayının `details`'ine
  `kalibrasyon_dogrulanmadi: true` yazılır ve ekranda metre "≈" ile gösterilir. Metre iddiası
  ya ölçülmüş hataya dayanır ya da açıkça "doğrulanmadı" diye işaretlenir (K26).
- **Kontrol ölçümü (F2, yalnız S7 "kalibrasyon ve şeritle kontrol ölçümü sahada yapılabilir"
  ise kodlanır; yoksa docs/07):** kalibrasyon ekranında operatör zeminde iki nokta seçer ve
  aralarını şeritle ölçüp girer. Sistem homografiyle hesaplar ve hatayı yüzde olarak kaydeder
  (`camera_calibrations.check_*` + `checked_at`, 007). Olaya `kalibrasyon_hatasi_yuzde` yazılır.
  Eşik uydurulmaz: sayı operatöre gösterilir, karar onundur. Tutarlılık için üç kod değişikliği
  gerekir: (1) yeniden kalibrasyon kaydı (`kameralar.py:453-465`, bugün yalnız `image_points`,
  `world_points`, `homography`, `calibrated_at` günceller) `check_*` sütunlarını NULL yapar,
  yoksa eski homografiyle ölçülmüş hata yeni olaylara "ölçülmüş" diye yazılırdı; (2) yapılandırma
  damgası (`supervizor.py:333`, bugün yalnız `MAX(calibrated_at)`) `MAX(checked_at)`'i de okur;
  (3) `Kalibrasyon` (`tipler.py:80-84`, yalnız `homografi`) `hata_yuzde: float | None` alır ve
  `_kalibrasyonu_yukle` (`supervizor.py:497-507`, yalnız `SELECT homography`) onu da okur. Her
  birine bir test.
- R21 düzeltmesi: mesafe kuralı pasif bölgeyi de denetler (`mesafe.py:34`). `hiz_mps=None`
  "duruyor" sayılmaya devam eder (`:60`); bu kaçırma yönünde bilinçli bir sapmadır ve docs/03'e
  yazılır.

---

## 7. Uyarı kanalları ve Bluetooth yöneticisi (mevcut anons adaptörleriyle ilişki; kanal listesi ve hangileri bu turda; garanti kuralı; Bluetooth: Linux'ta bluetoothctl/BlueZ yaklaşımı, Docker gereksinimleri, yeniden bağlanma, sağlık; Windows/Mac davranışı; test sesi)

### 7.1 Mevcut adaptörlerle ilişki

| §4.6 | Bugün | v2 (F4) |
|---|---|---|
| `AlertChannel.name` | `ad` özniteliği | aynen |
| `AlertChannel.send(event)` | `cal(anahtar, metin, ses_dosyasi)` (`anons.py:51`, `:125`, `:241`) | aynı imza + isteğe bağlı `olay: dict \| None = None`; eski adaptörler yok sayar, webhook kullanır. "Anonsu Dene" yolu (`anons_web.py:166`) değişmez |
| `AlertChannel.health()` | yok | `saglik() -> bool \| None` (True bağlı, False koptu, None bilinmiyor); `ses_cihazlari.cihaz_bagli_mi`'nin üç durumlu tasarımı (`:98-110`) korunur |
| `AlertDispatcher` | `AnonsYoneticisi` (`anons.py:275`) | **aynı sınıf, aynı genel API** (`duyur`, `hemen_cal`, `bolge_sec`, `son_sonuc`, `ad`). Korunan iç noktalar: `duyur(kamera_id, kamera_alani, zaman_s, mesaj)` konumsal imzası (yeni bilgi yalnız `olay=None` anahtar kelimesiyle), `_cal_ve_kaydet` (tek kanal çal + kaydet). Değişen iç noktalar: `_anonscu` ve `_hedef_anonscu` (bugün yalnız HTTP adresini değiştirir, `:338-349`) kanal satırlarına geçer. **"Kırılmadan evrilir" iddiası geri alındı:** testlerin bir kısmı iç yapıya bağlı ve F2/F4'te bilinçli güncellenir (§4.6: `test_anons_baglama.py:116`, `test_uyari_ve_anons.py:196`, `test_platform_uyumu.py:195`, `test_komuta_uyari_ve_anons.py:405-456`) |
| Hoparlör bölgeleri | `speaker_zones` + `bolge_sec` (`:245`, ilk eşleşeni döndürür); yalnız HTTP'de anlamlı (`:338-349`) | bölüm başına kanal satırı (`kind`, `device`); çoğul `bolgeleri_sec`; "Tüm fabrika" satırı (`area=''`) kurulumun varsayılan kanalıdır ve `.env ANONS*`'ın yerini alır (K22) |

### 7.2 Kanal listesi

| Kanal | Bu turda mı | Sınıf | Sağlık sinyali |
|---|---|---|---|
| Ekran (dashboard) | **Evet**, her zaman açık, kapatılamaz; **garantiye sayılmaz** (§7.4) | SSE `olaylar_web.py:98` + `canli.js` + `uyari.js`; F2'de komuta kabuğu da yükler | ≥1 bağlı SSE istemcisi (üreteç açılışta sayacı artırır, `finally`'de azaltır); yalnız bilgi olarak gösterilir. Kontrol Paneli başlangıçta izleme penceresini kendisi açtığı için (`dalsan_launcher.py:990` → `/` → `ana_sayfa.html:124` `canli.js` → `canli.js:18` `EventSource`) bu sayaç simge durumundaki bir pencereyle de ≥1 olur; garantiye sayılmamasının nedeni budur. HTTP/1.1'de tarayıcı başına 6 bağlantı sınırı docs/06'ya yazılır |
| Ses kartı: kablolu ya da Bluetooth sink | **Evet** | `SesKartiAnonscu(device)` | Linux: satırın **zorunlu** hedef sink'i (`device`) `pactl list short sinks`'te var mı (`ses_cihazlari.py:142-159`); bluez sink'inde adres deseniyle eşlenir (profil soneki yeniden bağlanmada değişebilir, DOĞRULANMADI). "Boş = varsayılan sink" seçeneği **kalkar**: `pactl get-default-sink` o anki etkin varsayılanı döndürdüğü için denetim totolojikti; Bluetooth hoparlör koparsa ses sunucusu varsayılanı dahili çıkışa ya da `auto_null`'a devredebilir (Ubuntu 24.04'te `module-switch-on-connect` yüklü, docs/16:319; hedef sunucuda DOĞRULANMADI) ve `paplay` "ok" dönerdi. Satır `paplay --device=<device>` ile yalnız o sink'e çalar; sink yoksa False. Eski boş kayıt (R37 öncesi) `None` ("beklenen çıkış bilinmiyor") olur, asla `True` değil. Çalıcı yoksa (container, R36) False. macOS/Windows: None (§7.7) |
| IP hoparlör | **Evet** | `HttpAnonscu(address)` | Adresin host:port'una TCP bağlantısı ≤3 sn (belgelenmiş sabit; ses çalmaz; `kamera.py` `_on_kontrol` deseni) + son gönderimin sonucu. Adres önce R30 doğrulamasından geçer (F4a; loopback/link-local reddi). "Ulaşılabilir" duyuldu demek değildir |
| Webhook | **Yalnız S4 "alıcı sistem var" ise** kodlanır; yoksa docs/07 | yeni `WebhookAnonscu`: JSON gövde (olay kodu, önem, kamera id, bölüm, zaman, olay id, aşama), `X-Dalsan-Zaman` ve `X-Dalsan-Imza: sha256=HMAC(sır, zaman + "." + gövde)`; stdlib `hmac`/`hashlib`; `http_gonder` (`anons.py:197`) yeniden kullanılır; sır yalnız `.env` ve günlüğe yazılmaz; adres R30 doğrulamasından geçer | Son gönderimin sonucu |
| Mesajlaşma (e-posta/SMS/Telegram) | Hayır | — | docs/07 #4 |
| Işıklı kule (GPIO/Modbus) | Hayır | — | donanım belirsiz; docs/07'ye yeni satır |
| SIP/ONVIF | Hayır | — | E4 |

Webhook kodlanırsa sistem olaylarını da (CAMERA_DOWN, ANALYSIS_STALLED, AUDIO_CHANNEL_DOWN,
ALERT_UNDELIVERED) taşır; ekran başında 7x24 kimse yoksa ekran dışındaki tek yol budur (S4).
S4 "alıcı yok" derse sistem olayları ekranda, sistem şeridinde, Kontrol Paneli'nde ve günlükte
kalır; bu sınır §15'e yazılıdır.

### 7.3 Dağıtıcı davranışı

1. **Yönlendirme:** olayın bölümü `cameras.area`'dan. Olay o bölümün **tüm** etkin ses/HTTP
   kanallarına gider; ekran ve (varsa) webhook her olayda ayrıca alır. Bölümde sağlıklı ses
   kanalı yoksa geri düşüş "Tüm fabrika" satırıdır (`area` boş). Bu satır, 009 sonrası ilk
   açılışta bugünkü `.env ANONS` / `ANONS_SES_CIHAZI` / `ANONS_HTTP_ADRESI` değerlerinden bir
   kez oluşturulur (hiç "Tüm fabrika" satırı yoksa ve `ANONS != null` ise; aktarım günlüğe
   yazılır); böylece bugünkü kurulumun duyulur davranışı aynen sürer ve kanal bilgisinin tek yeri
   `speaker_zones` olur (K22). Geri düşülecek satır da yoksa `/saglik` `yedek_ses_kanali_yok`;
   hiç sesli kanal yoksa `sesli_kanal_yok` (Ç39).
2. **Kanal başına tek işçi:** her kanalın bir `queue.PriorityQueue`'su ve tek işçi iş parçacığı
   var. Aynı çıkışta aynı anda tek ses çalar; farklı bölümlerin hoparlörleri birbirini beklemez.
   Sıra: önem (critical 0 … low 3), sonra kuyruğa giriş zamanı.
3. **CRITICAL kesme:** ses kartı çalıcısı `subprocess.run` (`anons.py:140`) yerine `Popen` +
   100 ms `poll`. Kuyruğa CRITICAL düşünce çalan düşük öncelikli ses `terminate` edilir.
   Windows'ta `winsound.PlaySound(None, 0)`. HTTP isteği kesilemez; yalnız sıra öne alınır
   (5 sn zaman aşımı, `anons.py:210`).
4. **Bayat sesi atma:** kuyrukta `ANONS_BEKLEME_SN`'den (mevcut, 30, `ayarlar.py:314`) uzun
   bekleyen, critical olmayan öğe çalınmaz, `stale` diye kaydedilir. Geçmiş bir durumu anlatan
   anons da bir yanlış alarm türüdür.
5. **Hız sınırı (yalnız S23'te değer verilirse kodlanır):** `ANONS_DAKIKA_SINIRI` kanal
   başına; critical muaf. Değer verilmezse kod yazılmaz, docs/07'ye satır.
6. **Birleştirme (yalnız S23'te değer verilirse kodlanır):** `ANONS_BIRLESTIRME_SN`
   penceresinde aynı (mesaj anahtarı, kanal) öğeler bir kez çalar. Metin taşıyan kanallar
   (ekran, webhook, HTTP `{metin}`) sayıyı alır ("2 kişi baretsiz"); WAV sabit olduğu için
   sayıyı söyleyemez (dürüst sınır).
7. **Tekrar bastırma:** GÖREV "aynı olay `cooldown_s` içinde tekrar çalınmaz" der; bunu olay
   düzeyinde durum makinesi ve değerlendiricinin kural cooldown'u zaten sağlar
   (`acildi` bir kez, `hatirlatma` yalnız cooldown dolunca). Dağıtıcıda bugünkü (kamera, mesaj)
   bastırması (`anons.py:313-314`, `ANONS_BEKLEME_SN`) **kanal eklenerek** korunur, çünkü
   birleştirme kodlanmadıkça aynı bölgedeki on kişinin on ayrı anonsunu önleyen tek şey odur.
   İki değişiklik: (a) **critical `acildi` aşaması bastırmadan muaftır**; aynı kamerada ikinci,
   ayrı bir forklift–kişi yakınlığı sesli duyurulmadan kalmaz; (b) bastırma **yalnız başarılı**
   çalmada tüketilir (bugün başarısızda da tükeniyor, R20) ve bastırılan deneme
   `alert_deliveries.result='suppressed_cooldown'` olarak iz bırakır.
8. **Hatırlatma:** §6.3'teki `hatirlatma` aşaması yalnız ses kanallarına gider.
9. **Gölge mod** değişmez (`supervizor.py:555`): olay yazılır, dağıtıcıya gitmez; yalnız
   `alert_deliveries.result='shadow'` yazılır ki "anons çalsaydı" sayısı bilinsin.
10. **Kayıt:** her deneme `alert_deliveries`'e (009) yazılır; bu docs/07 #16'yı kapatır.
    `_son_anonsu_yaz` (`anons.py:368`) gibi kendi kısa bağlantısını açar.
11. **Kapanış:** süreç kapanırken kuyruk boşaltılır (en fazla birkaç saniye beklenir,
    critical önce).

### 7.4 Garanti kuralı ve kanal sağlığı

**Kanal durum makinesi** (`anons-saglik` iş parçacığı, `ANONS_SAGLIK_ARALIGI_SN` = 10; `pactl`
çağrıları 5 sn zaman aşımlı, `ses_cihazlari.py:49`):

```
BAGLI ──False──▶ SUPHELI ──(kesintisiz False ≥ ANONS_KOPUK_ESIGI_SN=30)──▶ KOPTU  [AUDIO_CHANNEL_DOWN bir kez]
  ▲                 │True                                                    │
  └─────────────────┘                                  (2 ardışık True) ─────┘   [AUDIO_CHANNEL_UP]
None ──▶ BILINMIYOR   olay YOK · ekranda gri · garanti göstergesinde sağlıklı SAYILMAZ · gönderim yine DENENİR
```

Sonuç `speaker_zones.health` sütununa yazılır. Mac/Windows geliştirme makinesi `None` döndüğü
için sahte arıza üretmez.

**Garanti (iki parça):**

- **(a) Sesli/uzak garanti.** Gölgede olmayan **her** güvenlik olayı (önemden bağımsız; önceki
  sürümdeki "medium ve üstü" daraltması kaldırıldı, çünkü önem kural formundan seçilebiliyor ve
  "low" seçmek bir kuralı garantinin dışına itiyordu) için dağıtım bittiğinde en az bir **sesli
  ya da uzak** kanal "ok" olmalıdır: ses kartında çalıcı 0 ile döndü; HTTP ve (varsa) webhook'ta
  2xx. `suppressed_cooldown` garanti için "ok" sayılır: bastırma yalnız başarılı çalmada
  tüketildiği için aynı (kamera, mesaj) anonsu o kanaldan son `ANONS_BEKLEME_SN` içinde zaten
  duyurulmuştur. `stale` sayılmaz. Hiçbiri ok değilse: `ALERT_UNDELIVERED` sistem olayı (`ULASMAYAN_UYARI_ARALIGI_SN` hız
  sınırıyla), CRITICAL günlük, `/saglik` `hazir=false, sorunlar=["uyari_ulasmiyor"]`. Kontrol
  Paneli bu satırı kırmızı gösterir.
- **(b) Ekran ayrı gösterilir** ve garantiye sayılmaz. Nedeni: ekranın "ok" sayılması için olay
  satırının yazılması ve ≥1 SSE istemcisinin bağlı olması yetiyordu; Kontrol Paneli izleme
  penceresini kendisi açtığı için (§7.2) bütün ses kanalları ölse bile garanti hep "sağlanmış"
  görünür, kırmızı "uyarı kanalı yok" şeridi de ona bakan hiç kimseye görünmezdi. Görünür sayfa
  nabzı (`document.visibilityState`) eklenmez; ekran garantiye girmediği için gereksiz parça
  olurdu.

**Sürekli gösterge:** "şu an en az bir sesli/uzak kanal sağlıklı mı?" sorusu olaydan **önce**
`/saglik` `uyari_garantisi` alanında (`true` / `false` / `null` = doğrulanamıyor, ör. Windows'ta
sağlık hep `None`) ve her komuta ekranındaki sistem şeridinde görünür. Kontrol Paneli `false`'ta
kırmızı, `null`'da gri satır gösterir.

**Dürüst sınır:** "ok" kanala teslimdir, duyulduğu anlamına gelmez (docs/14 §8). `paplay`'in kopuk
Bluetooth sink'e sıfır dışı kodla döndüğü DOĞRULANMADI (AUDIT §11 #11); hedef sunucuda sınanır.

**"Bluetooth tek kanal olamaz" (GÖREV §7, Ç38):** ekran garantiye sayılmadığı için bu yasak artık
biçimsel olarak karşılanmış sayılmaz. Sesli/uzak kanalların tümü Bluetooth sink'i, `None` ya da
KOPTU durumundaysa `/saglik` `sorunlar`'a `tek_kanal_bluetooth` (ya da hiç yoksa
`sesli_kanal_yok`) eklenir; bu, yalnız Anons sayfasında değil sistem şeridinde, Kontrol
Paneli'nde ve kurulum listesinde (`kilavuz.py:339` `kurulum_durumu`) kırmızı görünür. Dağıtıcı
çalmayı reddetmez; reddetmek hiç ses çıkmaması demekti. Bu tercih operatöre sorulur (S32).

### 7.5 Bluetooth yöneticisi (Linux)

**Varsayılan (E2 ile uyumlu, S8):** eşleştirme ve `trust` işletim sisteminde, bir kez yapılır
(docs/14 §2.1.1). DALSAN şunları yapar:

1. **Cihaz seçimi:** hoparlör bölgesi formunda bağlı sink'ler listelenir (`ses_cihazlari.py`);
   o anki varsayılan sink önceden seçili gelir. Seçilen sink adı `speaker_zones.device`'a
   (`kind='ses_karti'`) yazılır ve Linux'ta **boş bırakılamaz** (§7.2: varsayılanı izlemek
   totolojik). Değer listeye karşı doğrulanmaz: kapalı hoparlör listede görünmez ve doğrulama
   seçimi silerdi (`anons_web.py:95-97` gerekçesinin aynısı). `hoparlorler.py:32` adres
   doğrulaması `kind='http'` satırlarına daralır.
2. **MAC ayrıca saklanmaz:** sink adından çözülür. PipeWire'da `bluez_output.<AA_BB_…>…`,
   PulseAudio'da `bluez_sink.<adres>.<profil>` (docs/16 §4); önek koda sabit yazılmaz, adres
   deseni aranır. `device` boş olamadığı için Bluetooth satırında MAC her zaman çözülebilir.
3. **Yeniden bağlanma bekçisi — koşullu (K23):** yalnız S9'da hoparlörün kapatılıp açılınca
   kendiliğinden bağlanmadığı görülürse **ve** S29'da container'da ses yolu (A) ya da host
   kurulumu seçilirse yazılır; aksi hâlde docs/07'ye satır olur ve yalnız kopmanın algılanması
   (R37, `AUDIO_CHANNEL_DOWN`) kalır (docs/16 §4 öneri 1). Yazılırsa Linux'ta bluez sink'li her
   satırda çalışır (açma anahtarı yok; `anons-saglik` yoklamasının içinde): sink listede yoksa
   `bluetoothctl info <MAC>` çalışır (`-t` **yok**,
   çıkış kodu anlamlı; cihaz yoksa `EXIT_FAILURE`); `^\s*Connected:\s*no$` görülürse
   `bluetoothctl connect <MAC>`. Bekleme 1 → 2 → 4 … en çok 60 sn (§4.6). BlueZ kendiliğinden
   yalnız bağlantı kaybında dener (7 deneme, 1–64 sn), hoparlörün kapatılıp açılmasını kapsamaz;
   bekçi bu boşluğu doldurur. `trust` şarttır; docs/14'e yazılır.
4. **Kütüphane yok:** `bleak` A2DP yapamaz; `dbus-fast` yalnız alt süreç yetmezse.
5. **Ses seviyesi yok** (docs/14 §8; S9).

**E2 geri alınırsa (S8 "evet"):** "Tara / eşleştir" ekranı yine `subprocess` ve `bluetoothctl`
ile yazılır: tarama `bluetoothctl -t 10 scan on` (bu kipte çıkış kodu hep 0, `[NEW] Device`
satırları ayrıştırılır); taramadan sonraki 30 sn içinde `-t`'siz `pair`, `trust`, `connect`
(aksi hâlde `TemporaryTimeout` cihazı siler); `-a` yazılmaz (etkisiz); PIN isteyen hoparlör
desteklenmez ve operatör OS ayarına yönlendirilir; `connect MAC a2dp-sink` biçimi BlueZ 5.82'den
önce yok, kullanılmaz.

**Ekransız sunucu:** PipeWire kullanılıyorsa WirePlumber `main-systemwide` profili ya da
`monitor.bluez.seat-monitoring = disabled` gerekir; PulseAudio'da önce mevcut `default.pa`
okunur (docs/16 §4). Kurulum kontrol listesi: `bluetoothctl --version`, `pactl info`, `id -u`,
`/etc/bluetooth/main.conf`.

### 7.6 Docker gereksinimleri

Fabrika imajında bugün ses aracı yok (`Dockerfile:10-12`, R36); `docker-compose.yml` yalnız
`/dev/snd` (ALSA) önerir, ALSA Bluetooth'u görmez. v2'de bu durum **sessiz kalmaz**: ses kartı
kanalı açılıştan 30 sn sonra `AUDIO_CHANNEL_DOWN` üretir. Kalıcı çözüm için üç yol; tasarım
varsayılanı (A), seçim operatörün (S29):

- **(A) Container'da ses — VARSAYILAN** (CLAUDE.md §4 "fabrikada tek container" ve docs/09 #4
  ile uyumlu olan tek yol): imaja `pulseaudio-utils` (ve yalnız bekçi yazılırsa `bluez`
  istemcisi; paket adları DOĞRULANMADI) eklenir; host'un Pulse/PipeWire soketi bağlanır,
  `PULSE_SERVER` tanımlanır, container host UID'siyle çalışır; bekçi için
  `-v /run/dbus:/run/dbus:ro`. `--privileged`, `--net=host`, `NET_ADMIN`, `NET_RAW`
  **verilmez** (docs/16 §4). İmaj derlenmedi; yol hedef sunucuda sınanana kadar DOĞRULANMADI.
- **(B1) Yalnız IP hoparlör:** container'a ses aracı girmez; Bluetooth hoparlör fabrikada
  **kullanılamaz** (operatörün doğrudan isteği karşılanmaz, açıkça yazılır: Ç35, §15).
- **(B2) systemd/host kurulumu:** "daha az parça" **değildir**: host'ta Python ortamı, systemd
  birimi ve imajdan ayrı bir güncelleme yolu, imaja tek apt paketi eklemekten fazla parçadır.
  CLAUDE.md §4 değişikliği gerektirir; yalnız operatör açıkça isterse (S1, S29).

### 7.7 Windows / macOS

- Eşleştirme ve yeniden bağlanma işletim sistemindedir. Windows'ta programatik eşleştirmede
  sistem diyaloğu her zaman çıkar (docs/16 §4).
- macOS: ses kartı kanalının sağlığı varsayılan çıkışa bakar (`system_profiler`, `ses_cihazlari`);
  "beklenen çıkış" girilmişse ve varsayılan başka bir cihazsa False; okunamazsa None. Alanın
  gerçek değerleri DOĞRULANMADI (AUDIT §11 #28).
- Windows: varsayılan çıkış ek modülsüz okunamadığı için sağlık **her zaman None** ("bilinmiyor",
  gri rozet). Bu platformda `uyari_garantisi` `null`'dır (doğrulanamıyor, gri); ekran garantiye
  sayılmadığı için garantinin "sağlandığı" iddia edilmez. Sahada Bluetooth önerilmez. Cihaz
  seçimi (WASAPI) yoktur (Ç43).
- Windows çalma yolu F2'de PowerShell `-Command` metni (`anons.py:72-83`) yerine stdlib
  `winsound.PlaySound(yol, SND_FILENAME)` olur; enjeksiyon yüzeyi kalkar.

### 7.8 Test sesi

- Kanal tablosunda her satırda kendi "Test sesi" düğmesi; ses o kanaldan çıkar.
- R39 düzeltmesi: test sesi bellekteki eski ayara değil formdaki/satırdaki cihaza çalar
  (bugün `anons_web.py:119` eski çıkışa çalıyor).
- Sonuç ekranda "yazılım gecikmesi: … ms" olarak gösterilir (§7.10) ve `alert_deliveries`'e
  `stage='test'`, `event_code=NULL` ile yazılır (test sesinin olay kodu yoktur, §8.3).

### 7.9 Türkçe ses

- **Sabit mesaj:** insan sesiyle kaydedilmiş WAV, `veri/sesler/` altında
  (`announcement_messages.audio_file`, docs/14 §2.3). 007 üç yeni mesaj satırını tohumlar
  (F2'de kurulan ek hazır kurallar onlara bağlanabilsin diye; 009'da olsaydı F2 kuralları
  `announcement_id=NULL` doğar ve kimse onları sonradan bağlamazdı); metinler taslaktır, son
  hâlini İSG belirler (S21). macOS `say`, Windows sesleri ve piper dfki
  müşteriye giden varlık olarak kullanılmaz (docs/16 §3).
- **Dinamik metin:** tarayıcı `speechSynthesis` `tr-TR` (`uyari.js:70-78`; çevrimdışı Türkçe
  sesin varlığı istemci işletim sistemine bağlı, DOĞRULANMADI) ve HTTP cihazının kendi TTS'i
  (`{metin}` yer tutucusu, `anons.py:159`).
- **Sunucu TTS yok** (E3). Operatör E3'ü geri alırsa: ayrı venv, `subprocess`, asla `import`
  (GPL); ve bugün ticari kullanılabilir Türkçe piper sesi olmadığı ayrıca bilinmeli.

### 7.10 Gecikme ölçümü

- **Yazılım kısmı ölçülür:** kare damgası (`kamera.py:310`) → olay → kuyruk → çalıcının ya da
  isteğin başlaması; `alert_deliveries.frame_to_start_ms`. `/saglik` ve Anons sayfasında p50/p90.
- **A2DP ve hoparlörün kendi tamponu yazılımdan ölçülemez.** Saha prosedürü (docs/06): bir kişi
  yasak alana adım atar; telefon aynı karede ekranı ve hoparlörü kaydeder; ekrandaki bant ile ses
  arasındaki kare sayısı sayılır. "100–250 ms" bir ölçüm değildir (docs/16 §4, P9); yazılmaz.

---

## 8. Veri modeli değişiklikleri (007_*.sql taslağı, mevcut tablolarla ilişkisi)

### 8.1 Mevcut tablolarla ilişki

| Tablo | Bugün | v2 | Göç |
|---|---|---|---|
| `zones` | `zone_type` CHECK 6 tip (`sema/001:50-52`) | CHECK kalkar; +`crossing`, +`ppe_exempt` | 007 (yeniden kurma, işaret satırı) |
| `events` | anlık olay; `status` inceleme durumu (`001:105-106`) | `event_code`, `severity`, `resolved_at`; F5'te `hold`, `hold_reason`. `status` CHECK'ine dokunulmaz; yaşam durumu `resolved_at IS NULL` demektir | 007, 010 |
| `rules` | `severity` DEFAULT `'warning'`, ölü (`001:87`) | canlanır; `'warning'` = olay kodunun varsayılanı; tablo yeniden kurulmaz; 008'de yalnız ADD COLUMN | 008 |
| `camera_calibrations` | 4 nokta + homografi | + kontrol ölçümü dört sütun (`check_*`, `checked_at`; S7) | 007 |
| `announcement_messages` | `updated_at` yok (R19) | `updated_at` damgaya girer; 3 yeni mesaj | 007 |
| `analysis_hours` | yok | yeni: kamera × saat analiz edilen süre | 007 |
| `ppe_collection_gate` | yok (toplama ön koşulsuz açık) | yeni: tek satırlık KKD veri toplama kapısı (K17) | 007 |
| `ppe_samples` | etiket, kaynak | + `person_height_px`, `sharpness`, `hard_case` | 008 |
| `rules` (ek) | — | + `approved_model_version` (KKD kapısından geçen model sürümü, §5.7) | 008 |
| `speaker_zones` | bölüm → HTTP adresi (`sema/002:30-40`) | + `kind`, `device`, `health`, `health_changed_at`; "Tüm fabrika" satırı `.env ANONS*`'ın yerini alır | 009 |
| `alert_deliveries` | yok | yeni: teslim ve gecikme kaydı (docs/07 #16) | 009 |
| `purge_log`, `access_log` | yok | yeni (KVKK) | 010 |

Yeni sütunlara CHECK konmaz (R24); değer listeleri Python'da tek yerde doğrulanır. Zaman
sütunlarına SQL DEFAULT verilmez (`zaman.py` yazar). Betikler `BEGIN/COMMIT` içermez.

### 8.2 `backend/sema/007_olay_yasam_dongusu.sql` taslağı (Faz 2)

Bu taslak, 001–006 uygulanmış ve içinde 1 kamera, 3 bölge, 4 kural, 10 olay bulunan bir kopya
veritabanına gerçek `veritabani.semayi_uygula()` ile uygulanarak denendi (proje dışı geçici
klasörde): bölge ve kural sayısı değişmedi, 10 olayın kural bağı korundu, `foreign_key_check`
boş döndü, açık olay kalmadı; sonrasında bir bölge silinince ona bağlı kuralların CASCADE ile
silindiği, yani yabancı anahtarın yerinde olduğu görüldü. **Düzeltme turundan sonra**
(`ppe_collection_gate`, `checked_at`, üç mesaj tohumu, kısmi olmayan indeks; 008'de
`approved_model_version`; 009'da boş bırakılabilir `event_code`) 007–010 aynı yöntemle yeniden
uygulandı: on sürüm kaydı, bölge 3 / kural 4, kural bağı korundu, `foreign_key_check` boş, açık
olay 0, mesaj 8, kapı satırı `(1, 0)`, `event_code` NULL test satırı yazılabildi, CASCADE yerinde;
`EXPLAIN QUERY PLAN` hem `resolved_at > ?` hem `resolved_at IS NULL` için
`idx_events_resolved`'ı kullanıyor.

```sql
-- 007_olay_yasam_dongusu.sql  (Faz 2)
--
-- İKİ İŞ:
--  1) zones YENİDEN KURULUR: zone_type CHECK (001_ilk.sql:50-52) kalkar. Tipin tek
--     doğruluk kaynağı artık saf katmanda app/rules/tipler.py BOLGE_TIPI_KODLARI
--     (web/ortak.py BOLGE_TIPLERI yalnız Türkçe ad eşler); yazım yolu
--     web/kameralar.py:_bolge_tipi_dogrula (:563-565). Yeni tipler: crossing, ppe_exempt.
--  2) EKLEMELİ: events, camera_calibrations, announcement_messages sütunları +
--     3 yeni anons mesajı + analysis_hours ve ppe_collection_gate tabloları.
--
-- TEHLİKE (005 ile aynı): rules.zone_id → zones ON DELETE CASCADE (001:84, 005:52).
-- Yabancı anahtar AÇIKKEN `DROP TABLE zones` bölgeye bağlı TÜM kuralları siler.
-- İşaret satırı zorunlu: app/veritabani.py betiği işlem DIŞINDA foreign_keys=OFF ile
-- çalıştırır (:132), sonra foreign_key_check yapar (:139). DİKKAT: denetim COMMIT'ten
-- SONRA koşar; bozukluk bulunursa açılış durur ama veritabanı yazılmıştır. Bu yüzden
-- v2'de işaretli betikten ÖNCE otomatik yedek alınır (docs/17 §8.4).
--
-- DALSAN-SEMA: YABANCI-ANAHTAR-KAPALI
--
-- Betikler BEGIN/COMMIT İÇERMEZ; sarmalamayı app/veritabani.py yapar.

-- ------------------------------------------------------------ 1) zones
CREATE TABLE zones_yeni (
    id         INTEGER PRIMARY KEY,
    camera_id  INTEGER NOT NULL
               REFERENCES cameras (id) ON DELETE CASCADE, -- bölge kamerasız yaşayamaz
    name       TEXT    NOT NULL,
    -- CHECK YOK (bilerek, docs/17 §4.5). Geçerli değerler: pedestrian_path,
    -- loading_area, truck_parking, vehicle_area, ppe_required, restricted,
    -- crossing, ppe_exempt
    zone_type  TEXT    NOT NULL,
    polygon    TEXT    NOT NULL,   -- JSON: normalize (0-1) [[x,y], ...], en az 3 nokta
    enabled    INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT    NOT NULL    -- ISO-8601 UTC
);

-- Sütunlar TEK TEK (005:63-65 gerekçesi). id'ler korunur → rules.zone_id geçerli kalır.
INSERT INTO zones_yeni (id, camera_id, name, zone_type, polygon, enabled, updated_at)
SELECT id, camera_id, name, zone_type, polygon, enabled, updated_at FROM zones;

DROP TABLE zones;

ALTER TABLE zones_yeni RENAME TO zones;
-- (001'de zones üzerinde indeks yok; yeniden kurulacak indeks yok.)

-- ------------------------------------------------------------ 2) events
-- PPE_NO_HELMET … CAMERA_DOWN (rules/olay_kodu.py). NULL = 007 öncesi olay.
ALTER TABLE events ADD COLUMN event_code  TEXT;
-- critical | high | medium | low | system (Python'da doğrulanır)
ALTER TABLE events ADD COLUMN severity    TEXT;
-- ISO-8601 UTC. NULL = olay SÜRÜYOR. Anlık olaylarda occurred_at ile aynı.
ALTER TABLE events ADD COLUMN resolved_at TEXT;

-- 007 öncesi olayların hepsi anlıktı; "sürüyor" görünmesinler.
UPDATE events SET resolved_at = occurred_at WHERE resolved_at IS NULL;

CREATE INDEX idx_events_code_occurred ON events (event_code, occurred_at);
-- KISMİ DEĞİL: hem açılışta "asılı" olayları kapatma / "sürüyor" filtresi
-- (resolved_at IS NULL) hem SSE'nin saniyelik "resolved_at > son bakış" sorgusu
-- (olaylar_web.py:108-134) aynı indeksi kullanır. Kısmi indeks ikinci sorguya
-- yaramaz ve her bağlı sekme her saniye tabloyu tarardı (maliyet ölçülecek).
CREATE INDEX idx_events_resolved ON events (resolved_at);

-- ------------------------------------------------------------ 3) analysis_hours
-- "Yanlış alarm ≤ 2 / saat / kamera" ve çalışma süresi (§4.8) için PAYDA.
-- Süpervizör birkaç dakikada bir upsert eder (INSERT … ON CONFLICT DO UPDATE).
CREATE TABLE analysis_hours (
    camera_id        INTEGER NOT NULL,   -- FK YOK: kamera silinse de ölçüm geçmişi kalır
    hour_utc         TEXT    NOT NULL,   -- 'YYYY-MM-DDTHH'
    -- Tespitçi yüklüyken işlenen ardışık kareler arasındaki süreler toplanır;
    -- kopukluk ve model yokluğu boşlukları SAYILMAZ.
    analyzed_s       REAL    NOT NULL DEFAULT 0,
    frames_processed INTEGER NOT NULL DEFAULT 0,
    frames_failed    INTEGER NOT NULL DEFAULT 0,   -- hat.isle istisnası (supervizor.py:529-532)
    PRIMARY KEY (camera_id, hour_utc)
);

-- ------------------------------------------------------------ 4) camera_calibrations
-- (Yalnız S7 "kontrol ölçümü sahada yapılabilir" ise; değilse bu blok 007'ye girmez.)
-- Metre iddiasının dayanağı: zeminde iki nokta + şeritle ölçülen gerçek mesafe.
-- NULL = doğrulanmadı → ekranda "≈", olayda kalibrasyon_dogrulanmadi.
-- Yeniden kalibrasyon (web/kameralar.py:453-465) bu dört sütunu NULL yapar.
ALTER TABLE camera_calibrations ADD COLUMN check_points     TEXT;  -- JSON [[x,y],[x,y]] normalize
ALTER TABLE camera_calibrations ADD COLUMN check_distance_m REAL;
ALTER TABLE camera_calibrations ADD COLUMN check_error_pct  REAL;  -- |hesaplanan − ölçülen| / ölçülen × 100
ALTER TABLE camera_calibrations ADD COLUMN checked_at       TEXT;  -- ISO-8601 UTC; damgaya girer

-- ------------------------------------------------------------ 5) announcement_messages
-- R19: mesaj ya da WAV değişikliği canlıya insin; damgaya (supervizor.py:329-341)
-- COALESCE(MAX(updated_at), '') olarak girer. Yazan yol: web/anons_web.py:159.
ALTER TABLE announcement_messages ADD COLUMN updated_at TEXT;
-- F2'deki ek hazır kurallar (yaya yolunda araç, araç yolunda yaya) bunlara bağlanır;
-- bu yüzden 009'da değil burada. Metinler TASLAK (S21).
INSERT OR IGNORE INTO announcement_messages (key, text) VALUES
    ('vehicle_on_walkway',     'Dikkat, yaya yolunda araç var.'),
    ('person_in_vehicle_lane', 'Lütfen araç yolundan çıkınız.'),
    ('restricted_entry',       'Bu alana giriş yasaktır.');

-- ------------------------------------------------------------ 6) ppe_collection_gate
-- KKD veri toplama kapısı (K17). .env'de DEĞİL: çalışırken açılıp kapanır, Docker'da
-- da yazılabilir. Tek satır (id = 1); _kkd_ornekle her örnekten önce okur.
CREATE TABLE ppe_collection_gate (
    id         INTEGER PRIMARY KEY,   -- her zaman 1
    enabled    INTEGER NOT NULL DEFAULT 0,
    changed_at TEXT,                  -- ISO-8601 UTC; NULL = hiç değiştirilmedi
    note       TEXT                   -- "Rev.02 imzalandı" onay metni
);
-- Başlangıç: kapalı (S10 varsayılanı). S10 "açık kalsın" derse 1 yazılır.
INSERT INTO ppe_collection_gate (id, enabled) VALUES (1, 0);

-- rules: ŞEMA DEĞİŞMEZ. severity DEFAULT 'warning' kalır; kodda "olay kodunun
-- varsayılanı" demektir. Veri güncellenmez.
```

### 8.3 Sonraki göçlerin özeti (008–010)

Aynı deneme veritabanına 007'nin ardından uygulandı; hatasız geçti, `foreign_key_check` boş.

```sql
-- 008_kkd_veri.sql (Faz 3) — yalnız ADD COLUMN
ALTER TABLE ppe_samples ADD COLUMN person_height_px INTEGER;
ALTER TABLE ppe_samples ADD COLUMN sharpness        REAL;  -- Laplacian varyansı
ALTER TABLE ppe_samples ADD COLUMN hard_case        TEXT;  -- white_cap | reflective_jacket | night_glare | backpack | raincoat | driver_cab …
-- KKD kapısından geçen model sürümü (dosya adı + sha256[:12]); NULL = hiç onaylanmadı.
-- params'a konmaz: params kural imzasına girer ve cooldown'u sıfırlardı (motor.py:76-86).
ALTER TABLE rules       ADD COLUMN approved_model_version TEXT;

-- 009_uyari_kanallari.sql (Faz 4) — yalnız ADD COLUMN / CREATE
-- Mevcut satırlar HTTP satırıdır (002); DEFAULT 'http' onları doğru sınıflar.
ALTER TABLE speaker_zones ADD COLUMN kind              TEXT NOT NULL DEFAULT 'http';  -- http | ses_karti
-- ses_karti: hedef sink adı, Linux'ta ZORUNLU (Python doğrular). '' yalnız R37 öncesi
-- aktarılmış kayıtta kalabilir ve sağlıkta "bilinmiyor" (None) sayılır, asla "bağlı" değil.
ALTER TABLE speaker_zones ADD COLUMN device            TEXT NOT NULL DEFAULT '';
ALTER TABLE speaker_zones ADD COLUMN health            TEXT;                          -- ok | down | unknown
ALTER TABLE speaker_zones ADD COLUMN health_changed_at TEXT;
-- .env ANONS / ANONS_SES_CIHAZI / ANONS_HTTP_ADRESI → "Tüm fabrika" satırı aktarımı SQL
-- ile yapılamaz (.env'i SQL okuyamaz): 009'dan sonraki ilk açılışta Python bir kez yapar.
CREATE TABLE alert_deliveries (
    id                INTEGER PRIMARY KEY,
    -- NULL = olay satırı YAZILAMADI ama uyarı yine gönderildi (fail-safe, §3.5)
    -- ya da test sesi. Bu satırları bakım queued_at'e göre siler.
    event_id          INTEGER REFERENCES events (id) ON DELETE CASCADE,
    -- NULL YALNIZ test sesinde (stage='test'); fail-safe satırında kod doludur.
    event_code        TEXT,
    speaker_zone_id   INTEGER REFERENCES speaker_zones (id) ON DELETE SET NULL,
    channel           TEXT    NOT NULL,  -- ekran | ses_karti | http | webhook
    -- OlayGecisi.asama ile aynı liste (§6.3) + test
    stage             TEXT    NOT NULL,  -- acildi | hatirlatma | kapandi | test
    -- ok | failed | shadow | stale | rate_limited | coalesced | preempted | fallback |
    -- no_listener | suppressed_cooldown
    result            TEXT    NOT NULL,
    detail            TEXT,              -- MASKELİ: adres ve şifre yazılmaz (R18)
    queued_at         TEXT    NOT NULL,
    started_at        TEXT,
    finished_at       TEXT,
    frame_to_start_ms INTEGER            -- kare yakalama → çalıcı/istek başlangıcı (yalnız YAZILIM)
);
CREATE INDEX idx_alert_deliveries_event  ON alert_deliveries (event_id);
CREATE INDEX idx_alert_deliveries_queued ON alert_deliveries (queued_at);

-- 010_kvkk_izleri.sql (Faz 5) — yalnız ADD COLUMN / CREATE
ALTER TABLE events ADD COLUMN hold        INTEGER NOT NULL DEFAULT 0;  -- 1 = saklama temizliğinden muaf
ALTER TABLE events ADD COLUMN hold_reason TEXT;
CREATE TABLE purge_log (          -- kişisel veri içermez; en az 3 yıl (Silme Yön. m.7/3)
    id              INTEGER PRIMARY KEY,
    ran_at          TEXT    NOT NULL,
    events_deleted  INTEGER NOT NULL,
    photos_deleted  INTEGER NOT NULL,
    samples_deleted INTEGER NOT NULL,
    held_skipped    INTEGER NOT NULL,
    policy          TEXT    NOT NULL  -- JSON: o anki saklama gün sayıları
);
CREATE TABLE access_log (         -- KVKK m.12 denetim izi
    id     INTEGER PRIMARY KEY,
    at     TEXT NOT NULL,
    client TEXT NOT NULL,         -- tek şifreli sistemde "kim" = istemci adresi
    -- view_snapshot | view_ppe_crop | export_csv | export_dataset | settings_change |
    -- rule_change | hold_change | ppe_collection_gate
    action TEXT NOT NULL,
    target TEXT                   -- ör. 'event:123'; FK YOK: olay silinse de iz kalır
);
CREATE INDEX idx_access_log_at ON access_log (at);
```

Kullanılmayacak sütun bugünden açılmaz (CLAUDE.md §7): her göç, onu kullanan fazla birlikte gelir.

### 8.4 Göç güvenliği

- **Otomatik yedek:** `veritabani.semayi_uygula` (`:85`) işaret satırı (`YABANCI_ANAHTAR_KAPALI`,
  `:35`) taşıyan bir betiği uygulamadan önce veritabanını SQLite backup API'siyle kopyalar
  (`rotalar.py:145-157` "Yedekle" ile aynı yöntem). Gerekçe: denetim (`:139`) COMMIT'ten
  (`:134`) sonra koştuğu için bozukluk bulunduğunda tek kurtarma yolu yedektir. **Yalnız kurulu
  bir veritabanına göç yapılıyorsa** (`sema_surumu` boş değilse) yedek alınır: 005 (ve 007)
  işareti her yeni kurulumda da uygulanıyor (`005:29`), koşulsuz yedek her ilk kurulumda ve
  testlerde `semayi_uygula`'nın her çağrısında (uygulamada 1, testlerde ~21 yer) boş bir yedek
  bırakır ve "Yedekten Geri Yükle" listesini kirletirdi. `semayi_uygula`'nın veri klasörünü bilen
  bir parametresi yok; hedef klasör `PRAGMA database_list`'ten öğrenilen dosya yolundan türetilir
  (`<db klasörü>/yedekler/`); bellek içi veritabanında yedek alınmaz.
- **Test:** `tests/test_veritabani.py`'ye 006 verili bir veritabanına 007 uygulama testi: bölge ve
  kural sayısı aynı, `rule_id`/`zone_id` bağları aynı, `foreign_key_check` boş, eski olaylarda
  `resolved_at = occurred_at`, bölge silinince kural CASCADE ile gider. Ayrıca "boş veritabanında
  yedek dosyası oluşmaz" ve "kurulu veritabanında işaretli betikten önce yedek oluşur".
- **`_eski_kurulum` yardımcısı düzeltilir** (`test_veritabani.py:132-139`): bugün yalnız verilen
  önekle başlayan betiği atlıyor. 007 taslağıyla ölçüldü: "eski" veritabanı 001–004 + 006 + 007
  ile kuruluyor, 005 en son uygulanıyor; testler yine yeşil kaldığı için sadakat kaybı
  görünmüyor. Yardımcı yalnız sıralı listede verilen önekten **önce** gelen betikleri kopyalar;
  007 göç testi de bu düzeltilmiş yardımcıyla yazılır (yoksa 008–010'u da içerirdi).

---

## 9. Güvenilirlik, sağlık, metrikler, günlük (en az parça ile: /saglik genişletme mi /healthz mi; metrik biçimi; watchdog)

### 9.1 `/saglik` genişler, `/healthz` açılmaz

Karar: mevcut `GET /saglik` (`rotalar.py:129-141`, kimliksiz `acik_router`) **her koşulda 200** ve
`durum: "calisiyor"` döndürmeye devam eder; Kontrol Paneli'nin `bizim_sunucumuz_mu`
(`dalsan_launcher.py:266-277`) sözleşmesi budur. Gövde genişler:

```json
{
  "durum": "calisiyor",
  "analiz": true,
  "model": "hazir",
  "hazir": true,
  "sorunlar": [],
  "analiz_tur_yasi_sn": 0.1,
  "uyari_garantisi": true,
  "bos_disk_gb": 27.4,
  "kameralar": [
    {"id": 1, "durum": "online", "okunan_fps": 6.0, "islenen_fps": 6.0,
     "isle_p50_ms": 80, "isle_p90_ms": 130, "son_kare_yasi_sn": 0.2}
  ],
  "kanallar": [{"ad": "Rampa hoparlörü", "tur": "ses_karti", "saglik": "ok"}]
}
```

(Değerler biçim örneğidir, ölçüm değildir.) `sorunlar` Türkçe ekrana çevrilecek sabit kodlardır:
`analiz_takildi`, `analiz_olu`, `model_yuklenemedi`, `veritabani_acilamadi`, `olay_yazilamadi`,
`uyari_ulasmiyor`, `ort_paket_cakismasi`, `kritik_kural_pasif` (§6.4); F4'te `sesli_kanal_yok`,
`yedek_ses_kanali_yok` (Ç39), `tek_kanal_bluetooth` (Ç38). `kanallar` F4'te gelir.
`uyari_garantisi` üç değerlidir: `true` / `false` / `null` (doğrulanamıyor) ve yalnız sesli/uzak
kanallara bakar (§7.4).

- **Kimliksiz gövde dardır.** `/saglik` kimliksiz `acik_router`'dadır (AUDIT §4.6); bugünkü üç
  alanlı gövdeyi kamera durumları, kanal adları ve disk bilgisiyle genişletmek oturumsuz bilgi
  ifşasını büyütürdü. Kimliksiz yanıt yalnız `durum`, `analiz`, `model`, `hazir`,
  `uyari_garantisi`, `sorunlar` alanlarını döner (Kontrol Paneli ve Docker healthcheck'in
  ihtiyacı bu kadardır). `kameralar`, `kanallar`, `bos_disk_gb`, `analiz_tur_yasi_sn` yalnız
  `?ayrinti=1` **ve** geçerli oturumla (şifre boşsa `oturum_gerekli` zaten serbest bırakır) gelir.

- `GET /saglik?hazirlik=1`: `hazir` false ise 503. `docker-compose.yml` healthcheck buna geçer.
  Docker "unhealthy" durumda container'ı yeniden başlatmaz (docs/16 §8); bu yalnız görünürlüktür,
  yeniden başlatmayı bekçi yapar.
- Kontrol Paneli `hazir=false` ya da `uyari_garantisi=false` olunca durum satırında kırmızı,
  `uyari_garantisi=null` olunca gri Türkçe bir satır gösterir; `bizim_sunucumuz_mu` değişmez.
- `okunan_fps` bugünkü `measured_fps`'tir (okuma hızı, `kamera.py:312-315`); `islenen_fps` yeni
  sayaçtır. Bugün kılavuz "işlenen" der ama okunanı gösterir (R12, `kilavuz.py:71-72`); ikisi
  ayrılır.

### 9.2 Metrik biçimi

- **Varsayılan:** metrik `/saglik` JSON'undadır; ayrıca Komuta → Sağlık ekranında (`komuta.py:756`)
  işlenen fps ve `isle()` p90 sütunu.
- **Müşteride Prometheus varsa (S13):** elle yazılmış `GET /metrics`, metin biçimi 0.0.4,
  `Content-Type: text/plain; version=0.0.4` **zorunlu** (Prometheus 3), etiket kamera id'si (adı
  değil), 5–8 gauge/counter. `prometheus_client` eklenmez (docs/16 §8). Kimlik: çerez tabanlı
  oturum Prometheus'ta çalışmaz (şifre tanımlıysa kazıma olmaz, uç ya işlevsiz kalır ya da
  kimliksiz açılmaya zorlanır); bu yüzden `.env METRIK_ANAHTARI` ile `Authorization: Bearer`
  denetlenir, anahtar boşsa uç 404'tür. S13 "hayır" ise hiçbiri yazılmaz.

### 9.3 Bekçi ve systemd

§3.6. systemd birimi `docs/06:83`'te `app.main:uygulama` yazıyor ve bugün başlamıyor; F2a'da
`app.main:app` olur (R26, koşulsuz). Bildirim/bekçi entegrasyonu yalnız S1 "systemd" ise F5'te:
`Type=simple` + `WatchdogSec=120` + `NotifyAccess=main` + stdlib `WATCHDOG=1`. Varsayılan Docker
dağıtımında bu kod yazılmaz (docs/07).

### 9.4 Günlük

- Uygulama günlüğü zaten JSON (`loglama.py:45-62`, `:84-101`). F2'de `loglama.kur` `uvicorn`,
  `uvicorn.error`, `uvicorn.access` logger'larını da aynı `_JsonSatirBicimi`'ne bağlar; uvicorn'a
  log-config dosyası verilmez. Dosya, dönüş (5 MB × 3) ve biçim değişmez.
- HTTP anons adresi günlükte maskelenir (R18, `anons.py:217`).
- Webhook sırrı ve şifreler hiçbir günlük satırına yazılmaz; bir test bunu kilitler.

### 9.5 Diğer güvenilirlik maddeleri

| Madde | Karar | Faz |
|---|---|---|
| Kayıtların analiz iş parçacığındaki maliyeti (R11) | F2'de `ihlal_yaz` süresi de sayaçlara girer. Yazıcı kuyruğu **yalnız ölçüm gerektirirse** F5'te yazılır (en az parça) | F2 ölç, F5 karar |
| Disk koruması | Bugün yalnız uyarı (`supervizor.py:748-753`). F5: `DISK_DUR_GB` (öneri 1; `DISK_UYARI_GB`=5'in altında, SQLite WAL ve günlük dönüşüne pay bırakır; S35) altında kanıt fotoğrafı ve KKD kırpığı yazımı durur; olay satırı yazılmaya devam eder. Varsayılan "kapalı" değildir: §4.9 disk doluluk korumasını ister | F5 |
| NTP | Kod değil belge: docs/06'ya chrony / systemd-timesyncd adımı; saat kaymasının kanıt zamanını bozduğu yazılır | F5 |
| Düzgün kapanış | Kapanışta: kamera iş parçacıkları → açık olaylar `kapanis` ile kapanır → `SYSTEM_STOPPED` → anons kuyruğu boşaltılır | F2/F4 |
| Sıcak yükleme | Restart'sız istenen her ayar SQLite'ta (5 sn damga); `.env` restart ister (bugünkü düzen, Ayarlar sayfası söyler) | — |
| `sample_fps` değişince hat sıfırlanması (R34) | Takipçi yeniden kurulmadan fps güncellenir | F5 |
| `_canli_sayim` kilitsiz okuma (R28) | `list(...)` kopyası | F2 |

---

## 10. KVKK ve güvenlik (docs/KVKK.md içeriği taslağı; yüz bulanıklaştırma; erişim)

> Bu bölüm hukuki tavsiye değildir. docs/16 §7'deki Kurul kararlarının çoğu yalnız arama
> özetleriyle doğrulanabildi. Her satır avukat teyidi bekler.

### 10.1 `docs/18-KVKK.md` taslağı

E8 gereği dosya adı `docs/KVKK.md` değil `docs/18-KVKK.md`. Tek sayfalık uyum kartı; her satır
"yükümlülük → kaynak → üründeki karşılığı → avukat teyidi":

| Yükümlülük | Kaynak (docs/16 §7) | Üründeki karşılığı |
|---|---|---|
| Hukuki dayanak | KVKK m.5/2-ç (6331 m.4'ten doğan hukuki yükümlülük) ve m.5/2-f (meşru menfaat); 2022/797 | Aydınlatma metninde yazılır; açık rıza kutusu **konmaz** (2026/347) |
| Aydınlatma | m.10'un beş unsuru; Tebliğ m.5; katmanlı yöntem (2020 duyurusu); 2023/2007'deki levha uygulaması | İki katman: kameralı alanlarda sarı zeminli kamera levhası (veri sorumlusu, "İSG amacıyla görüntü işlenmektedir", tam metnin yeri) + tam metin. Mevcut CCTV metni varsa yeni amaç için güncellenir (Tebliğ m.5/1-b) |
| Yüz tanıma yok | m.4 ölçülülük; 2022/797. (2026/921 yalnız mesai takibini kapsar; ancak benzetme yoluyla anılır) | Yüz kırpığı, gömme vektörü, Re-ID, iz → personel eşlemesi hiçbir tabloya yazılmaz; ByteTrack iz numarası oturum içi geçici kimliktir. Bir "saklanmayanlar" testi şemayı denetler |
| Ses işlenmez | 2020/212; 2023/2007; 8770 | `cv2.VideoCapture` ses okumaz; belgeye "sistem ses işlemez" yazılır |
| Amaç sınırı | 8770 (sürekli gözetim, performans/disiplin takibi meşru amaç değil); docs/00 "hukuki" maddesi | Yalnız İSG olayları; kişi bazlı rapor ve "en çok ihlal yapan" yok; uyarılar bölge/konum bazlı |
| İnsan onayı | m.11/1-g (yalnız otomatik analize itiraz) | Kişi aleyhine sonuç doğmadan İSG uzmanı incelemesi şartı aydınlatma metnine yazılır; ürün yalnız "inceleme" işaretleri sunar |
| Çalışan görüşü | 6331 m.18/1-b | Kurulum listesine "İSG kurulu / çalışan temsilcisine danışıldı" maddesi (uygulanabilirliği avukata sorulur) |
| Saklama | m.4/2-d, m.7; Silme Yönetmeliği (6 ayda bir periyodik imha; imha kaydı ≥3 yıl); sabit gün yok (P28) | `.env` 180/90/30/90 (`ayarlar.py:272-275`) değişmez, gün sayısını müşteri+avukat belirler (S5); bakım günlük; `purge_log` (F5) |
| Olay dondurma | 8770 ("hukuki süreçte yalnız ilgili kayıt") | `events.hold` ve "Dondur" düğmesi (F5); bakım dondurulmuşa dokunmaz |
| Erişim ve güvenlik | m.12; 2018/10; 8770 yetki matrisi | Tek şifre + `access_log` (F5); Faz 2a güvenlik düzeltmeleri |
| Mahremiyet alanları | 2022/797; 8769 (dar açı, maskeleme) | Kurulum listesinde "tuvalet, soyunma, duş, mescit, dinlenme, emzirme odası görüş alanında olamaz"; önce açı düzeltilir |
| Rol ve sözleşme | m.12/2 müşterek sorumluluk | DALSAN–müşteri veri işleyen sözleşmesi; bulut, telemetri, yurt dışı aktarım yok (tek dış bağlantı model indirme, `model_indir.py:21`) |
| Ağ bölümlendirmesi (§4.10 "belgelenir") | m.12 teknik tedbir; docs/05:47 (kamera VLAN'ı yalnız donanım gereksinimi olarak) | F5'te `docs/18-KVKK.md` ve docs/06'ya bölüm: kameralar ayrı VLAN'da; sunucu yalnız kamera VLAN'ına, yönetim ağına ve anons cihazlarına erişir; dışarıya tek çıkış model indirmedir (kurulumdan sonra kapatılabilir); uzaktan erişim yalnız docs/15'teki yolla. Kod değil belge; ağ ekibiyle birlikte doldurulur |
| KKD veri toplama | docs/00:63-64 (Rev.02) | SQLite `ppe_collection_gate` kapısı, restart'sız ve gecikmesiz kapanır (§5.8) |

### 10.2 Saklanmayanlar

Yüz kırpığı, yüz gömmesi, kişi adı/sicil, iz → personel eşlemesi, ses, ham video akışı (ADR-009;
bugün yalnız kullanıcının yüklediği test videoları var, bakım dışı: R23). Şemada bunları
taşıyabilecek bir sütun olmadığını doğrulayan test F2'de eklenir.

### 10.3 Yüz bulanıklaştırma

- **Yalnız S27 "evet" ise kodlanır** (o zaman `YUZ_BULANIKLASTIRMA` anahtarıyla); S27 "hayır" ya
  da cevapsızsa kod yazılmaz, docs/07'ye satır olur (CLAUDE.md §7 "ileride lazım diye" yok).
  Aşağıdaki kurallar kodlanırsa geçerlidir.
- Açılırsa yalnız **dışa aktarılan** görüntülere ve **KKD dışı** olayların kanıtına uygulanır.
  Canlı önizleme saklanmadığı için uygulanmaz (§4.10).
- **Çakışma:** docs/16 §6 öneri 5'teki "kişi kutusunun üst ~%20'si" yöntemi baret bölgesini de
  siler; KKD olayının incelemesi ve dolayısıyla precision ölçümü imkânsızlaşır. Bu yüzden KKD
  kanıtına ve KKD kırpıklarına uygulanmaz. KKD kırpıkları bunun yerine erişim kısıtı ve
  `access_log` ile korunur.
- **Yöntem:** önce modelsiz kutu üstü (uzak kamerada YuNet 10 px altı yüzü bulamaz); kalite
  yetmezse `cv2.FaceDetectorYN` + YuNet `2023mar` (MIT, 232.589 bayt, sha256 docs/16 §6;
  `2026may` OpenCV 5 ister). Ek pip paketi yok. Yüzün gerçekten kapandığı DOĞRULANMADI; 50
  örnekte ölçülecek.

### 10.4 Erişim ve denetim izi

- Tek yönetici şifresi kalır (`YONETICI_SIFRESI`, varsayılan boş, `.env.example:107`). Roller
  docs/07 #5'te (S5).
- F5: `/goruntuler/{yol}` (`olaylar_web.py:246`), KKD kırpığı, CSV ve veri seti dışa aktarımı,
  ayar/kural/dondurma değişikliği ve KKD toplama kapısı `access_log`'a yazılır. "Kim" tek şifreli
  sistemde istemci adresidir; bu sınır belgeye yazılır.
- Fabrika container'ında şifre zorunluluğu (R13): Docker `--host 0.0.0.0` sabit
  (`Dockerfile:40`), `SUNUCU_ADRESI` kilidi (`ayarlar.py:222-230`) orada işlemez. **F2a'ya
  alındı** (önceki sürümde F5'ti): container içinde `YONETICI_SIFRESI` boşsa açılış reddedilir
  (birkaç satır). Bugün compose portu `127.0.0.1:8080` bağladığı için (`docker-compose.yml:20`)
  varsayılan kurulum LAN'a kapalıdır; ama fabrikada başka ekranlardan erişim için port satırı
  değiştirildiği anda şifresiz sistem LAN'a açılır ve F2'den F5'e kadar herkes anonsu kapatabilir,
  kural ve bölge silebilirdi. Origin ara katmanı bunu kesmez (yalnız siteler arası isteği keser).

### 10.5 Güvenlik düzeltmeleri

| # | Bulgu (Faz 0) | Dosya:satır | Düzeltme | Faz |
|---|---|---|---|---|
| R7 | Kilit adresi koşulsuz `X-Forwarded-For`'un ilk değerinden | `web/giris.py:87-97` | Doğrudan bağlantı adresi (`istek.client.host`); vekil arkasında uvicorn `--proxy-headers --forwarded-allow-ips=<vekil>` | F2a |
| R9 | Yönetici şifresi `type="text"` ve değeriyle basılıyor | `templates/komuta_ayarlar.html:48`; `web/ayar_rotalari.py:95-100` | Alan türü `sifre`: `type="password"`, değer basılmaz, boş gönderim şifreyi değiştirmez | F2a |
| R8 | CSRF / Origin / Host denetimi yok | `uygulama.py:97-104` | Tek ara katman, iki kural. (1) **Host izin listesi** (AUDIT R8'in önerisi): her istekte `Host` (portsuz) `127.0.0.1`, `localhost`, `SUNUCU_ADRESI` ya da `.env IZINLI_SUNUCU_ADLARI` içinde değilse 421. Origin'i `Host`'la karşılaştırmak DNS rebinding'de hiçbir şey engellemez: saldırganın alan adı sunucunun adresine yeniden çözüldüğünde `Origin` ve `Host` aynı sahte adı taşır, `Sec-Fetch-Site` `same-origin` olur. (2) Durum değiştiren isteklerde (POST) `Origin` (yoksa `Referer`) host'u izin listesinde değilse, `Origin: null` ise ya da `Sec-Fetch-Site: cross-site` ise 403. **Üç başlığın üçü de yoksa istek geçer**: CSRF vektörü her zaman bir tarayıcıdır ve güncel tarayıcılar POST'ta `Origin`'i, sayfanın bastıramayacağı `Sec-Fetch-Site`'ı gönderir; başlıksız istek tarayıcı dışı istemcidir (curl, Starlette `TestClient`; `istemci.post` 25 test dosyasında kullanılıyor ve TestClient bu başlıkları göndermiyor). Uzaktan erişimde kullanılan adlar (docs/15) listeye yazılmalıdır, yoksa 421 (§15 risk 23) | F2a |
| — | FastAPI `/docs`, `/redoc`, `/openapi.json` kimliksiz açık (kod okuması; çalıştırılarak doğrulanmadı, AUDIT §11 #15) | `uygulama.py:93` | `FastAPI(..., docs_url=None, redoc_url=None, openapi_url=None)` | F2a |
| R4 | RTSP açılış/okuma zaman aşımı yok | `analiz/kamera.py:223` | `CAP_PROP_OPEN_TIMEOUT_MSEC` / `CAP_PROP_READ_TIMEOUT_MSEC` (5000/10000) | F2b |
| — | Windows PowerShell `-Command` metni dosya yolundan kuruluyor (hafifletilmiş enjeksiyon yüzeyi) | `olaylar/anons.py:72-83` | stdlib `winsound` | F2a |
| R14 | `.env` satır enjeksiyonu | `ayarlar.py:401-410` | `\n`, `\r` ve diğer kontrol karakterleri reddedilir | F2a |
| R15 | `compare_digest(str, str)` ASCII dışında `TypeError` — **DOĞRULANDI (yerel)**: `hmac.compare_digest('şifre','şifre')` → `TypeError: comparing strings with non-ASCII characters is not supported`. Şifre alanında ASCII denetimi yok (`ayarlar.py:211-215` yalnız uzunluk), yani Türkçe karakterli şifre ya da girişe Türkçe karakter yazan herkes 500 alır | `web/giris.py:197` | UTF-8 bayt karşılaştırma (`sifre.encode("utf-8")`); 2a'ya "ş içeren şifreyle giriş 500 değil 303" testi | F2a |
| R17 | Model bütünlüğü yok | `analiz/model_indir.py:22`, `:79-85`; `models/indir.sh` | `{ad: sha256}`; `sha256sum -c` | F2a |
| R26 | systemd yanlış sembol | `docs/06-OPERASYON.md:83` | `app.main:app` | F2a |
| R10 | Python üst sınırı yok | `masaustu/dalsan_launcher.py:209` | `(3,12) <= v < (3,13)` (CLAUDE.md §4 Python 3.12), ORT sürümünden bağımsız. Önceki sürümdeki "1.30.0'da `<3.15`" geri alındı: docs/16 (1.30.0 ORT engelini kaldırır ama "diğer paketler test edilmeli") ve Ç28 ("testler 3.12'de") ile çelişiyordu; 3.13+ ancak tam paket orada yeşil koşunca açılır | F2a |
| R13 | Container'da şifresiz açılış | `Dockerfile:40` | §10.4; container içinde `YONETICI_SIFRESI` boşsa açılış reddi | **F2a** (önceden F5) |
| R27 | Docker'da `.env` salt okunur tek dosya bağlanıyor; Ayarlar kaydı `replace()` ile yazıyor ve orada başarısız olur (AUDIT R27, kod okuması, DOĞRULANMADI) | `docker-compose.yml:24`; `ayarlar.py:430-433` | `.env` bir `ayar/` dizini içinde bağlanır (salt okunur değil); `ayarlar.py` yolu `resolve()` ile çözer, geçici dosya hedefle aynı dizinde oluşur. Olmazsa belgeye "Docker'da ayarlar sunucudaki dosyadan değiştirilir + yeniden başlatma" yazılır ve Ayarlar sayfası bunu söyler. İmaj derlenmedi | F2a |
| R16 | Çerez HMAC anahtarı yalnız şifreden | `web/giris.py:62-63` | Kuruluma özgü rastgele sır | F5 |
| R18 | RTSP şifresi formda açık; HTTP anons adresi günlükte | `kamera_detay.html:320`; `anons.py:217` | Maskeli form ve günlük | F5 (günlük kısmı F2) |
| R30 | SSRF | `web/hoparlorler.py:32-45` | Loopback / link-local reddi; F4'ün sunucu tarafı TCP sağlık yoklaması (10 sn'de bir) ve (varsa) webhook da aynı doğrulamadan geçer. Yüzey düzeltmeden önce büyümesin diye **dağıtıcıdan önce** | **F4a** (önceden F5) |
| R31 | CSV formül enjeksiyonu | `web/olaylar_web.py:145`; `web/rapor.py` | Hücre ön eki | F5 |
| R32 | Root kullanıcı; gereksiz `ffmpeg` apt paketi | `Dockerfile:10-14` | `USER`; `ffmpeg` RTSP provasından sonra kaldırılır | F5 |

---

## 11. Arayüz değişiklikleri (hangi sayfalar; Jinja2 + sade JS sınırı içinde)

Sınır: Jinja2 şablonu + sade JavaScript; yeni CSS/JS çatısı, Node.js, derleme adımı yok
(CLAUDE.md §4). Simgeler mevcut `static/vendor/` Lucide sprite'ından.

**Önbellek kuralı:** proje bütün statik çağrılarda tek bir ortak `?v=N` kullanır (bugün `?v=24`,
ör. `komuta_temel.html:17-19`, `ana_sayfa.html:123-124`). `test_arayuz_surumu_ve_model_mesaji.py`
sürümlerin **eşit** olduğunu denetler, **artırıldığını** denetlemez. JS/CSS değiştiren her alt
adımda (F2'de `uyari.js`, `canli.js`, `kamera_detay.js`, `stil.css` ve komuta kabuğuna eklenen
betikler) bütün şablonlardaki `?v=N` birlikte artırılır; yoksa tarayıcı önbellekteki eski JS'i
çalıştırır.

| Sayfa / dosya | Değişiklik | Faz |
|---|---|---|
| Komuta kabuğu `templates/komuta_temel.html` | `canli.js` + `uyari.js` + `#canli-durum` yüklenir (bugün yalnız `kilavuz.js:156`, `onay.js:164`); **sistem şeridi**: 5 sn'de bir `/saglik`; kırmızı = analiz yok / kamera koptu / sesli uyarı kanalı yok (`uyari_garantisi=false`, `sesli_kanal_yok`, `tek_kanal_bluetooth`) / kritik kural pasif, gri = sağlık doğrulanamıyor (`uyari_garantisi=null`). Ekranın kendisi garantiye sayılmadığı için şerit, bakan tarayıcının varlığıyla "yeşile" dönmez | F2 |
| `static/uyari.js` | Önem rengi; critical bandı 8 sn'de (`:94`) kapanmaz, olay bitene ya da tıklanana kadar durur; sistem olayları için ayrı bant (bugün `:104` yalnız `violation`); boş `catch`'ler (`:67`, `:77`) yerine ekranda "Sesli uyarı çalışmıyor" çipi (R41); ses kapalıyken kalıcı "Sesli uyarı KAPALI — açmak için tıklayın" çipi | F2 |
| Olaylar `olaylar.html`, `olaylar_web.py` | Olay kodu, önem, "sürüyor / bitti" rozeti ve filtresi; süre; eski olaylarda kural tipi adı | F2 |
| Kamera detayı `kamera_detay.html`, `kamera_detay.js`, `stil.css` | Bölge tipi listesinde "Yaya-araç geçidi" ve "KKD muaf alan" (iki yeni renk değişkeni); "yaya yolunda araç kuralı ekle", "araç yolunda yaya kuralı ekle" ek düğmeleri (gölge modda kurulur); kalibrasyon kontrol ölçümü alanı (S7 "evet" ise); kamera formunda örnekleme hızı varsayılanı `.env`'den | F2 |
| Kural formu `kural_form.html`, `kurallar.py` | Önem seçimi ("Varsayılan" = olay kodunun önemi; varsayılanın altına indirmek sarı uyarıyla onay ister ve F5'ten sonra `access_log`'a düşer); `bitis_s`, `gecit_haric`, `histerezis_m`; sınıf kutuları katalog + aktif modelden; varsayılanlar şemadan (R25) | F2 |
| Komuta → Sağlık (`komuta.py:756`) | Okunan ve işlenen fps ayrı; `isle()` p90; analiz durumu | F2 |
| Komuta → Olay rengi (`komuta.py:275`) | Önemden; inceleme durumu rozet olur | F2 |
| Ayarlar `komuta_ayarlar.html` | Şifre alanı; yeni `.env` anahtarları gruplar hâlinde (Takip, Kamera, Bekçi, KKD, Uyarı, Gizlilik) | F2–F5 |
| KKD `kkd.html`, `kkd_web.py` | Toplama kapısı (SQLite, restart'sız) + Rev.02 onayı; "Veri setini dışa aktar"; model adı/sürümü/sha256; gölge mod karnesi (olay sayısı, incelenen, **inceleme kapsamı %**, N, precision, kapı durumu ve hangi şartın eksik olduğu); zor örnek seçimi | F2 (kapı), F3 |
| Anons `anons.html`, `anons_web.py`; komuta anons `komuta_anons.html` | Kanal tablosu: tür, cihaz, üç durumlu rozet (yeşil "Bağlı" / kırmızı "Koptu" / gri "Bilinmiyor", R38); satır başına "Test sesi" (R39); son 24 saatte teslim oranı; kare→ses (yazılım) p50/p90; "Bluetooth tek sesli kanal" uyarısı; "Tüm fabrika" satırı bugünkü ses çıkışı seçiminin yerini alır. Aynı tablo komuta ekranında (R40: `ses_cikisi_baglami` → `anons_baglami`, `komuta.py:1211`) | F4 |
| Hoparlörler (`hoparlorler.py`) | Tür (IP hoparlör / ses kartı-Bluetooth) ve cihaz (bağlı sink listesinden, Linux'ta zorunlu, varsayılan sink önceden seçili) alanları | F4 |
| Kurulum listesi (`kilavuz.py:339`) | "Sesli kanal tanımlı değil", "Bluetooth tek sesli kanal olamaz", "Etkin mesafe/hız kuralı kalibrasyon bekliyor" kırmızı maddeleri; "mahremiyet alanı kontrolü" maddesi | F2/F4/F5 |
| Rapor `komuta_rapor.html`, `rapor.py` | Olay kodu başına yanlış alarm oranı ve inceleme kapsamı %; kamera × gün başına yanlış alarm / analiz saati yalnız inceleme kapsamı tam dilimlerde (§14), eksikse "ölçülemedi"; analiz edilen süre %; teslim istatistiği | F2/F4 |
| Olay detayı `olay_detay.html` | "Dondur (hukuki süreç)" düğmesi; kapanış sebebi | F5 |
| Ayarlar → KVKK | Erişim günlüğü listesi; imha günlüğü | F5 |
| Kontrol Paneli (`dalsan_launcher.py`) | `hazir=false` / `uyari_garantisi=false` kırmızı satırı | F2 |

---

## 12. Veri ve model planı (kullanılabilir veri setleri — yalnız ticari kullanıma uygun lisanslar; forklift/tır özel sınıfı yolu; export/kuantizasyon; model kartı)

### 12.1 Kullanılabilir kaynaklar

Yalnız ticari kurulumda kullanılabilir ya da koşulu yazılı olanlar. "Kullanılamaz" listesi kesindir
ve docs/16 karar tablosundadır; burada tekrarlanmaz. Özellikle §4.7'nin önerdiği üç KKD seti
(SH17 CC BY-NC-SA; CHV ve Pictor-PPE lisanssız) **kullanılmaz**; SHWD, SFCHD, GDUT-HWD,
Ultralytics Construction-PPE de öyle.

| Kaynak | Lisans (docs/16 doğrulama düzeyi) | Kullanım | Koşul |
|---|---|---|---|
| **DALSAN saha verisi** | Müşterinin; KVKK dayanağı ve Rev.02 şart | KKD ince ayarı ve **bütün** değerlendirme; forklift/tır ince ayarı | KKD veri toplama kapısı (`ppe_collection_gate`); S10 |
| **LOCO** (TUM) | CC0 1.0 (DOĞRULANDI) | forklift, `pallet_jack` ("pallet truck"), palet | `person` yok; el kamerası perspektifi; indirme bağlantısı bu ortamdan açılamadı |
| YOLOX kodu ve resmi ağırlıklar | Apache-2.0 (DOĞRULANDI) | Mevcut tespit; ince ayar başlangıcı | Ağırlıkların COCO/Flickr görüntü kökeni için hukuk görüşü (S20) |
| YuNet `2023mar` | MIT (DOĞRULANDI) | İsteğe bağlı yüz bulanıklaştırma | sha256 ile indirilir |
| Roboflow Construction Site Safety (`roboflow-universe-projects`) | CC BY 4.0 (DOĞRULANMADI, arama özeti) | **Koşullu:** yalnız KKD ön eğitimi | Sürüm sabitlenir; lisans satırının ekran görüntüsü `LICENSE-THIRD-PARTY`'ye; ürünle dağıtılmaz |
| Roboflow Safety Vests; HardHat & SafetyVest; Hard Hat Workers; Kaggle andrewmvd | DOĞRULANMADI | **Koşullu**, aynı kurallar; yalnız baret içerenler MVP'de gerekmiyorsa eklenmez | Köken kontrolü (SH17/Pictor/CHV izi varsa elenir) |
| LVIS forklift (id 470), COCO alt kümesi | Anotasyon CC BY 4.0; görüntüler COCO/Flickr | **Koşullu** | Hukuk görüşü |

"Public Domain" ya da CC0 etiketi görüntüdeki kişilerin mahremiyet haklarını kapsamaz (docs/16 §1).

### 12.2 KKD

§5. Sıra: politika (`docs/kkd-politika.md`) → planlı çekim + otomatik örnekleme → etiketleme →
kamera/gün bölmesi → (koşullu kamu setiyle ön eğitim) → DALSAN verisiyle ince ayar → HTML rapor →
gölge mod. Hedef veri miktarı docs/04 §4.5'tedir; bu belge yeni sayı koymaz.

### 12.3 Forklift / tır özel sınıfı yolu

1. Bugün forklift üretilmiyor; car/bus/truck tek "truck" (`tespit.py:26-36`). Bu sürede bilinen
   sınırlar: binek araç `VEHICLE_ON_WALKWAY` ve mesafe kuralını tetikler; sürücü muafiyeti yalnız
   "truck" görünen araçta çalışır.
2. Veri: müşteri kameralarından KVKK dayanaklı birkaç yüz kare (alan kayması için en değerlisi) +
   LOCO (forklift, pallet truck). LOCO'da `person` yok; kişi bilgisini unutmamak için COCO'dan
   `person`/`truck`/`car` içeren küçük bir alt küme stdlib ile süzülüp eklenir (docs/16 §2).
3. Eğitim: YOLOX depo klonu, ayrı venv, GPU'lu makine; `tools/train.py -f <Exp> … -c <ağırlık>`;
   sınıf başı sıfırdan başlar (docs/16 §2). COCO JSON birleştirme ve sınıf eşleme ~50 satırlık
   stdlib betiği (ürün dışı); betik saha karelerinde kamera+gün bölmesini zorlar ve kutu
   etiketleme kuralı docs/04 §5'in "tespit kutuları" alt bölümündedir (Ç45). Uzman işi, tek
   seferlik; runbook docs/04 §6 (Ç37, S31).
4. Sınıf sırası katalog kimliğine göre yazılır ve ONNX metadata'sına konur (§4.2). `loader` yalnız
   sahada varsa ve yalnız müşteri görüntüsüyle (S12).
5. **Güvenlik gerilemesi uyarısı:** car/truck ayrılınca forklift, model onu "car" sanarsa mesafe
   kuralından kaçabilir. Ayrım ancak saha ölçümünde forklift recall'u görüldükten sonra
   devreye alınır; o zamana kadar mesafe kuralının `object_classes`'ı araç grubunun tamamını alır.
6. Doğruluk (mAP50) yalnız etiketli saha test gününde ölçülür (§14); kutu etiketlemeyi kimin
   yapacağı S11.

### 12.4 Export, kuantizasyon, çalışma zamanı

- **Export:** resmi YOLOX ONNX dosyaları ORT 1.30 ile açılıyor (docs/16 §5). Kendi modelimizde
  decode kapalı, opset 11, batch 1; `export_onnx.py` PyTorch 2.5'te kaldırılan
  `torch.onnx._export`'u kullandığı için eğitim ortamında PyTorch ≤2.4 sabitlenir ya da çağrı
  `torch.onnx.export(..., dynamo=False)` olarak yamalanır.
- **ORT sürümü:** 1.19.2 → 1.30.0 (S19). Gerekçe: gömülü `onnx` CVE-2026-14647; aynı makinede
  `session.run` ~%25 hızlı (docs/16 §5, yerel ölçüm, hedef donanım değil). Intel Mac geliştirici
  varsa 1.23.2 (x86_64 macOS tekerleği olan son sürüm; CVE durumu DOĞRULANMADI).
- **GPU:** ayrı `backend/requirements-gpu.txt` (yalnız `onnxruntime-gpu[cuda,cudnn]`), Dockerfile
  `ARG` ile ayrı imaj; kurulum önce `pip uninstall -y onnxruntime` çalıştırır; açılışta
  `importlib.metadata` iki paket birlikteyse uyarır. 1.27+ CUDA 13 ister; sürücü CUDA 12'de
  kalacaksa 1.26.x (S1). `onnxruntime.preload_dlls()` yalnız `hasattr` ile korunarak çağrılır:
  fonksiyon 1.21 ve sonrasında var (docs/16:399), bugünkü 1.19.2'de **yok** (`.venv`'de
  `hasattr(onnxruntime, "preload_dlls")` → False, yerelde denendi); S19 "yükseltme yapılmasın"
  derse koşulsuz çağrı GPU açılışını `AttributeError` ile düşürürdü. GPU imajı pratikte ORT ≥ 1.21'e
  bağlıdır (S1, S19). Kurulumda tek karelik gerçek çıkarım duman testi; `get_providers()` tek
  başına yetmez.
- **TensorRT, OpenVINO, INT8:** MVP dışı (Ç24). INT8 denenecekse yalnız geliştirici makinesinde ve
  önce `lscpu | grep -i vnni`.
- **supervision** 0.25.1'de kalır; 0.31'e geçişte `trackers.ByteTrackTracker` (docs/07'ye satır).

### 12.5 Model kartı ve bütünlük

- Kart ONNX `custom_metadata_map`'te: sınıflar/başlar, veri penceresi, bölme özeti, test
  metrikleri, eğitim tarihi, kaynak veri setleri ve lisansları. Ayrı yan dosya ya da
  `models/<ad>/<sürüm>/` klasörü gerekmez.
- `BILINEN_MODELLER` `{ad: sha256}`; hazır YOLOX dosyalarının özetleri resmi yayından alınıp
  yazılır (değerleri bu belgede yok, uydurulmaz). KKD modeli sha256'sı yüklemede doğrulanır;
  uyuşmazsa model yüklenmez ve `MODEL_LOAD_FAILED` yazılır.
- `LICENSE-THIRD-PARTY`'ye: LOCO CC0, YuNet MIT, koşullu setlerin lisans kanıtları, reddedilen
  TTS ve veri setleri (tekrar denenmesin diye).

---

## 13. Fazlar 2–5: kapsam, testler, "operatör ne görecek" (tablo)

Her alt adım ayrı, küçük commit'lere bölünür (CLAUDE.md §8: bir adımda 10+ dosya değişiyorsa
bölünür). Kural mantığına dokunan her adımdan sonra `pytest tests/rules -q` çalışır ve çıktı
operatöre gösterilir. Her fazın sonunda tam paket ve `ruff` yeşil olur; §4.6'daki testler
bilinçli güncellenir. Fazdan önce Kontrol Paneli → Yedekle.

| Faz | Kapsam | Testler | Operatör ne görecek |
|---|---|---|---|
| **2a** Güvenlik tabanı | §10.5'teki F2a satırları (R7, R9, R8 Host izin listesi + Origin, `/docs`, PowerShell → winsound, R14, R15, R17, R26, R10 `<3.13`, **R13** container'da şifresiz açılış reddi, **R27** `.env` dizin bağlama); ORT sabiti (S19 cevabına göre); iki ORT paketi uyarısı; `tespit.py:103-117` EP hatası / bozuk dosya ayrımı; `?v=N` artırımı | `tests/test_guvenlik.py`: sahte XFF ile 6. deneme yine kilitli; yabancı Origin'li POST 403, aynı origin 303; `Host: evil.example` + aynı adlı Origin → 421 (DNS rebinding); `Origin: null` → 403; Origin/Referer/Sec-Fetch-Site'ın üçü de yok → geçer (tarayıcı dışı istemci); Ayarlar HTML'inde şifre değeri yok; boş şifre alanı eski şifreyi korur; `ş` içeren şifreyle giriş 500 değil 303; `\n` içeren `.env` değeri reddedilir; `/docs` 404; container kipinde şifresiz açılış reddedilir; `.env` sembolik bağla dizindeyken Ayarlar kaydı hedef dosyayı değiştirir. `test_ses_cikisi.py:88-93` ve `test_platform_uyumu.py:200-212` winsound'a göre yeniden yazılır. sha256 uyuşmazlığında Türkçe `ModelHatasi` | Ayarlar'da şifre kutusu noktalı ve boş; boş bırakıp Kaydet'e basınca eski şifreyle girilebilir. Tarayıcıda `/docs` açılmaz. Kontrol Paneli ve tüm sayfalar eskisi gibi açılır. Başka bir makineden sunucunun IP'siyle açmak isterseniz o adresi Ayarlar → İzinli sunucu adları'na yazmanız gerekir, yazılmamışsa sayfa "izin verilmeyen adres" der |
| **2b** Takip ve kamera | `TAKIP_HAFIZA_SN`; kayıp toleransı kurucu parametresi; RTSP zaman aşımları; kopukluk eşiği ikiye ayrılır; UP kararlılığı süpervizörde (`KAMERA_UP_KARARLILIK_SN`); R29; `kameralar.py:98` örnekleme hızı `.env`'den; işlenen fps, `isle()` ve `ihlal_yaz` süre sayaçları | `lost_track_buffer` formülü (6 fps × 2 sn = 12 kare); `VideoCapture`'a zaman aşımı parametreleri geçiyor (sahte cv2); sahte saatle çevrimiçi → 10 sn → çevrimdışı, ilk bağlantıda 60 sn tolerans; `_durumlari_yaz` UP olayını 5 sn kesintisiz kareden önce yazmaz; `test_kamera_kaynagi.py:32-39` iki ayrı eşikle güncellenir (§4.6); `tests/rules` 85 test değişmeden yeşil | Çalışan kameranın kablosunu çekin: ~10 sn içinde kamera "çevrimdışı" görünür ve Olaylar'a "Kamera çevrimdışı" düşer. Kabloyu takın: birkaç saniye sonra "tekrar çevrimiçi" |
| **2c** Şema 007 ve olay modeli | Otomatik yedek (yalnız kurulu veritabanında); 007 (üç mesaj tohumu, `ppe_collection_gate`, kısmi olmayan `resolved_at` indeksi dahil); `olay_kodu.py`, `olay_durumu.py`, `aktif_anahtarlar`, `gecisleri_al`; bölge tipi kodları `rules/tipler.py`'de; önem; geçit istisnası (`Baglam` değişmez); bağlamsal önem; mesafe histerezisi ve R21; kalibrasyon kontrol ölçümü (yalnız S7 "evet"); `kritik_kural_pasif`; `yazici` kod/önem/bitiş; açılış/kapanış kapatma; kodlu sistem olayları (`MODEL_LOAD_FAILED` iki yoldan, `SYSTEM_STARTED/STOPPED`); `crossing`, `ppe_exempt`; `EK_HAZIR_KURALLAR` (`HazirKural.golge`, INSERT `shadow_mode` yazar, yeni mesajlara bağlanır); `anons_web.py:159` `updated_at`; SSE yükü; olay rengi | `tests/rules/test_olay_durumu.py` (aç, hatırlat, kapat; `bitis_s`; kapanış sonrası cooldown; kayıp toleransı içinde kısa örtülmede olay bitmez; sınırda titreşen kişi tek olay; **KKD olayı gözlemler belirsize dönünce `belirsiz` sebebiyle kapanır, hatırlatma üretmez**); `test_olay_kodu.py` (sözlüğün tamamı); `rules/tipler` ↔ `web/ortak` bölge tipi anahtar eşitliği; geçitte ihlal yok; araç varken high; histerezis; `test_veritabani` 007 göç testi ve düzeltilmiş `_eski_kurulum` (§8.4); boş veritabanında yedek oluşmaz; ek hazır kural `shadow_mode=1` ve `announcement_id` dolu doğar; mesaj metni değişince süpervizör 5 sn içinde yeni metni kullanır; yeniden kalibrasyonda `check_*` NULL olur (S7); §4.6 test güncellemeleri (mesaj sayısı 5→8 şemadan türetilir); `test_saflik` yeşil | Güncellemeden önce ve sonra Kameralar'daki bölge ve kural sayısı aynı. Bölge tipi listesinde iki yeni seçenek. Yasak alana giren test videosunda Olaylar'da **tek** satır: "Yasak alana giriş — Yüksek — sürüyor"; kişi çıkınca "bitti" ve süresi. Anons kişi içerideyken kuralın bekleme süresi dolunca bir kez tekrarlar. Mesafe kuralı olan ama kalibrasyonu olmayan kamerada kurulum listesinde kırmızı "kalibrasyon bekleniyor" |
| **2d** Görünür arıza ve sağlık | Fail-safe sıra (§3.5, bellek kural haritası); `bekci.py`; `/saglik` genişler (kimliksiz dar gövde, `?ayrinti=1` + oturum), `?hazirlik=1`; compose healthcheck; uvicorn JSON günlüğü; komuta kabuğu `canli.js` + `uyari.js` + sistem şeridi; `uyari.js` R41; `ANALYSIS_DEGRADED` (`ANALIZ_YAVAS_SURE_SN`, `ANALIZ_HATA_ESIGI`); `analysis_hours`; launcher kırmızı/gri satırı | Sahte saatle bekçi takılmayı yakalar, masaüstü kipinde süreçten çıkmaz, sunucu kipinde `os._exit` çağrılır (monkeypatch); `/saglik` her durumda 200 ve `durum=calisiyor`, `bizim_sunucumuz_mu` bozulmaz; kimliksiz yanıtta `kameralar`/`kanallar` yok; `?hazirlik=1` 503; `ihlal_yaz` istisna fırlatınca `duyur` yine çağrılır; **kural satırı okunamazken (`_kural_kaydi` istisnası) de `duyur` çağrılır ve gölgedeki kural bellekten tanınıp susar**; `uvicorn.access` satırı JSON; `komuta_temel.html` iki betiği yüklüyor | `models/` içindeki model dosyasının adını değiştirip sistemi yeniden başlatın: her komuta ekranında kırmızı "Analiz yapılmıyor — model yüklenemedi" şeridi ve Olaylar'da bir sistem olayı. Tarayıcıda `http://127.0.0.1:8080/saglik?ayrinti=1`: her kamera için `islenen_fps` ve `isle_p90_ms`. Kontrol Paneli durum satırı yine "ÇALIŞIYOR". Komuta ekranlarında artık uyarı bandı çıkar |
| **2e** KVKK tabanı ve ölçüm | `ppe_collection_gate` kapısı (SQLite, `_kkd_ornekle` her örnekten önce okur) + piksel sınırı `min_person_height_px`'ten; `ppe_exempt` içindeki kişiden örnek alınmaz; `PPE_COLLECTION_CHANGED`; "saklanmayanlar" testi; sentetik senaryo takımı (`tests/fixtures/` + `tests/test_uctan_uca_olaylar.py`: sentetik mp4 + senaryolu sahte dedektör → beklenen olay JSON'u, kod/önem/başlangıç/bitiş ± tolerans); rapora yanlış alarm / analiz saati (yalnız inceleme kapsamı tam dilimler); docs/03, docs/06, docs/07 güncellemeleri | Kapı kapalıyken `ppe_samples`'a satır eklenmez; kapı kapatıldıktan sonraki **ilk** örnek denemesinde satır yazılmaz (gecikme yok); eşik altı boyda örnek alınmaz; `ppe_exempt` içindeki kişiden `ppe_samples` satırı yazılmaz; şemada yüz/gömme/personel sütunu yok; uçtan uca senaryolar geçer. Sahadan gelen her yanlış alarm buraya regresyon senaryosu olarak eklenir | KKD sayfasının üstünde "Veri toplama: KAPALI — Rev.02 onayı bekleniyor". Kutuyu işaretleyip açınca, yeniden başlatmadan, Olaylar'a "KKD veri toplama açıldı" düşer; kapatınca toplama hemen durur. Rapor'da her kamera için "analiz edilen saat" ve "yanlış alarm / saat" (inceleme eksikse "ölçülemedi") |
| **3a** KKD kapıları | Rev.02 teyidi; `docs/kkd-politika.md`; S3 (kapsam, sürücü) | — (belge) | Politika belgesini İSG ile birlikte doldurursunuz |
| **3b** KKD verisi | 008; örnekle kişi boyu/netlik; zor örnek etiketi; `egitim/veri_seti.py` (kamera+gün bölmesi, zip, manifest) | Aynı kamera ve gün iki kümede olamaz; manifest sha256 tutarlı | KKD sayfasında Var/Yok/Belirsiz + "zor örnek" seçimi; "Veri setini dışa aktar" zip indirir; içinde train/val/test kamera ve güne göre ayrılmış |
| **3c** KKD modeli | Ürün dışı eğitim (ayrı ortam); `kkd_siniflandirici.py` ORT; `KKD_MODEL_DOSYASI`; sha256; netlik ve örtüşme ölçümü; `hiz_kiyas`'a sınıflandırıcı turu | Sahte ORT oturumuyla başlar → `KkdGozlem`; görünmüyor / düşük olasılık / bulanık → belirsiz; model dosyası yoksa gözlem yok; sha256 uyuşmazlığı → model yüklenmez | Model konunca KKD sayfasında "Model: kkd-<sürüm>, doğrulandı". Önizlemede kutular yeşil / kırmızı / gri |
| **3d** KKD kararı | Kalem başına olay; `surucu_muaf`; `ppe_exempt` oyma (kural ve `kkd_bolgesinde_mi`); `max_kisi_ortusmesi` (None = kapalı); belirsizde kapanış; KKD hazır kuralı gölgeyle doğar; model sürümü değişince gölgeye dönüş (`approved_model_version`, `PPE_MODEL_CHANGED`); `kapsam=muaf_disi` **yalnız S3 dışlama kipini seçerse** | `tests/rules`: belirsiz asla olay üretmez (korunur); yalnız yelek yoksa yalnız `PPE_NO_VEST`; ikisi yoksa iki olay, iki cooldown; araç kutusundaki kişi → belirsiz; `ppe_exempt` içindeki kişi atlanır; örtüşme None iken `test_kkd.py` değişmez; onaylı sürümden farklı model yüklenince kural `shadow_mode=1` olur ve bir `PPE_MODEL_CHANGED` yazılır, cooldown sıfırlanmaz; (S3 seçerse) `muaf_disi` kipinde bölgesiz kural çalışır | Baretsiz yürüyen test kişisi 10–15 sn sonra Olaylar'da "Baret yok (gölge)"; hoparlör **çalmaz**. Forklift/tır içindeki kişi için olay çıkmaz. Kişi arkasını dönüp uzaklaşınca olay "bitti" olur, "sürüyor" kalmaz |
| **3e** KKD ölçümü | `egitim/degerlendirme.py` tek komutla HTML rapor; gölge karnesi (N, kapsama %); kapı (precision + gün + en az olay + incelenmemiş olay yok) | Rapor üreteci sahte tahminlerle beklenen karışıklık tablosunu verir; precision 0,89'da kapı kapalı; **1 doğru olay, %100 precision ama N < `KKD_KAPI_EN_AZ_OLAY` → kapı kapalı**; incelenmemiş olay varken kapı kapalı; model sürümü değişince sayaç sıfırlanır. Metrikler yalnız saha verisiyle ölçülür | Rapor'da baret ve yelek için ayrı yanlış alarm oranı; KKD karnesinde "Precision: ölçülen değer (N incelenmiş olay, kapsama %, model vX)". Şartlardan biri eksikse "Anonsu aç" hangi şartın eksik olduğunu yazarak gri |
| **4a** Dağıtıcı | (ilk alt adım) `.env ANONS*`'a bağlı testlerin kanal satırı fikstürüne geçirilmesi (§4.6); R30 SSRF reddi (dağıtıcıdan önce); 009; `.env ANONS*` → "Tüm fabrika" satırı tek seferlik aktarımı; `AnonsYoneticisi` evrimi (§7.3; `duyur` imzası ve `_cal_ve_kaydet` korunur); `saglik()`; `alert_deliveries`; `shadow` ve `suppressed_cooldown` kaydı; ekran kanalı istemci sayacı; kapanışta boşaltma | `tests/test_uyari_dagitici.py`: öncelik; aynı çıkışta eşzamanlı iki ses yok; critical çalan medium'u keser (sahte Popen); bayat öğe atılır; başarısız çalmada bastırma tükenmez; **aynı kamerada ikinci ayrı critical açılış bastırılmaz**, bastırılan medium `suppressed_cooldown` yazar; geri düşüş "Tüm fabrika" satırına; aktarım bir kez yapılır ve bugünkü `ANONS=ses_karti`/`http` kurulumunda aynı çıkış çalar; loopback hoparlör adresi reddedilir; olay satırı yazılamadığında teslim `event_id=NULL`. Mevcut anons testleri §4.6'daki bilinçli güncellemelerle yeşil | Aynı anda bir yakınlık (Kritik) ve bir yelek (Orta) ihlalinde önce yakınlık anonsu duyulur. Anons sayfasında son 24 saatte teslim oranı. Güncellemeden önce anonsun çaldığı çıkış, güncellemeden sonra "Tüm fabrika" satırında görünür ve aynı yerden çalar |
| **4b** Kanal sağlığı ve garanti | `anons-saglik`; DOWN/UP; `ALERT_UNDELIVERED` (`ULASMAYAN_UYARI_ARALIGI_SN`); R37 (sink zorunlu, boş = None), R38, R39, R40; `/saglik` `kanallar`, üç değerli `uyari_garantisi` (yalnız sesli/uzak kanallar), `sesli_kanal_yok`, `yedek_ses_kanali_yok`, `tek_kanal_bluetooth`; kurulum listesi maddeleri | Sahte saatle 29 sn False'ta olay yok, 30 sn'de tek DOWN; 2 True sonra UP; None olay üretmez ama garanti `null`; boş seçim → None (`test_ses_cikisi.py:160` güncellenir), asla True; **seçili bluez sink listeden kalktı, varsayılan alsa çıkışına geçti → False**; container benzetimi (çalıcı yok) = False; HTTP TCP reddi = False; hiç sesli kanal yokken `sesli_kanal_yok` ve ihlalde hız sınırlı `ALERT_UNDELIVERED` + CRITICAL günlük; **SSE istemcisi bağlıyken bile sesli kanallar ölüyse garanti `false`**; tek sesli kanal Bluetooth ise `tek_kanal_bluetooth` | Anons sayfasında her kanal için rozet. Hoparlörü kapatın: ~30–40 sn sonra rozet kırmızı ve Olaylar'a "Ses kanalı koptu: <ad>"; bu sırada ihlal olursa ses aynı bölümün başka kanalından ya da "Tüm fabrika" çıkışından gelir. Bütün hoparlörleri kapatıp ihlal üretin: izleme penceresi açık olsa da Kontrol Paneli'nde ve sistem şeridinde kırmızı "Uyarı hiçbir sesli kanala ulaşamadı" |
| **4c** Webhook (**yalnız S4 "alıcı sistem var" ise**; yoksa docs/07) | `WebhookAnonscu`; adres R30 doğrulamasından geçer | İmza alıcı tarafında doğrulanır; sır günlüğe düşmez; adres boşken kanal yok | `WEBHOOK_ADRESI` girilince test alıcısında imzalı JSON görülür |
| **4d** Bluetooth | Sink seçimi (zorunlu, varsayılan önceden seçili); MAC çözümü; kopma algısı; Linux yeniden bağlanma bekçisi **yalnız S9 (kendiliğinden bağlanmıyor) ve S29 ((A) ya da host) koşulları sağlanırsa**, yoksa docs/07; S8 "evet" ise tara/eşleştir ekranı ayrı adım | Sink adı iki önekte de bulunur ve adres deseniyle eşlenir; (bekçi yazılırsa) sahte `bluetoothctl` çıktılarıyla `Connected` ayrıştırma, geri çekilme 60 sn'de tavan, Linux dışında bekçi çalışmaz | Linux'ta Bluetooth hoparlörü kapatın: rozet kırmızı ve "Ses kanalı koptu". Açın: hoparlör kendiliğinden bağlanıyorsa (S9) ya da bekçi yazıldıysa en geç ~1 dk içinde rozet yeşile döner ve "Ses kanalı tekrar bağlandı" gelir |
| **4e** Container ses yolu, Türkçe WAV, saha ses testi | S29'a göre compose/Dockerfile (varsayılan (A): `pulseaudio-utils` + host ses soketi; `/run/dbus:ro` yalnız bekçi yazıldıysa); WAV'lar `veri/sesler/`'e; docs/14 (kanal tablosu, trust şartı, bağlama, sınırlar, lisans notu); gecikme prosedürü | Statik: compose ses bloğunda `--privileged` yok. Saha: docs/06 kabul listesi | Her bölümde test anonsunu duyarsınız; Anons sayfasında "kare→ses (yazılım) p90"; telefon videosu yöntemiyle hoparlör gecikmesini not edersiniz |
| **5a** Çalışma zamanı | GPU imajı (S1); tek paket kuralı; duman testi; `.venv` ve testler 3.12 | Hedef donanımda `get_providers()` CUDA içerir ve tek kare çıkarım başarılı (bu ortamda GPU yok, DOĞRULANMADI olarak işaretlenir); ORT çakışma uyarısı | "Sistem GPU'da çalışıyor" satırı; ya da "GPU istendi, CPU kullanılıyor" olayı |
| **5b** Güvenilirlik | `BEKCI_TEPKISI`; `DISK_DUR_GB` (öneri 1); NTP belgesi; R34; kayıt kuyruğu yalnız 2b ölçümü gerektirirse; systemd bildirimi **yalnız S1 "systemd" ise** (`Type=simple` + `WatchdogSec` + `NotifyAccess=main`, §3.6), yoksa docs/07 | disk eşiğinde fotoğraf yazılmaz, olay yazılır; (S1 systemd ise) sd_notify sahte soket `WATCHDOG=1` alır ve birim dosyası `Type=notify` içermez | Sunucuyu yeniden başlatın: sistem kendiliğinden açılır, `/saglik` "hazir: true". Olaylar'da "Sistem durdu" / "Sistem başladı" ve açık kalmış olayların "sistem durdu" sebebiyle kapandığı |
| **5c** KVKK | 010; Dondur düğmesi; `purge_log`; `access_log`; ağ bölümlendirmesi belgesi; `docs/18-KVKK.md`; mahremiyet kontrol maddesi; yüz bulanıklaştırma **yalnız S27 "evet" ise** | `hold=1` olay saklama süresi geçse de silinmez; her bakım koşusu `purge_log`'a bir satır; kanıt görüntüleme `access_log`'a düşer ve şifre/çerez içermez; (S27 evet ise) bulanıklaştırma açıkken KKD kanıtı değişmez, dışa aktarılan KKD dışı kanıtta yüz bölgesi değişir | Dondurulan olay süre dolsa da listede kalır; Ayarlar → KVKK'da "adres, saat, olay #123 görüntülendi" satırları ve imha günlüğü |
| **5d** Kalan güvenlik | R16, R18, R31, R32 (R13 ve R27 F2a'ya, R30 F4a'ya taşındı) | `=` ile başlayan CSV hücresi kaçışlı; RTSP şifresi formda maskeli; container root değil | — |
| **5e** Saha kabulü | Hedef donanımda `tests/hiz_kiyas`; tespit doğruluk takımı (`tests/dogruluk_kiyas/`, pytest kapısı değil, veri depoya girmez); uzun süreli çalışma provası (süre operatörle belirlenir); docs/06 saha kabul listesi | Ölçüm tabloları çalıştırılan komut + ham çıktıyla (GÖREV §9); hedef tutmazsa gerçek sayı, neden ve sonraki adım | Listeyi sahada madde madde işaretlersiniz: kamera açısı ve mahremiyet alanı, bölgelerin yerine oturması, kalibrasyon kontrol ölçümü, her bölümde anonsun duyulması, kamerayı kapatıp 10 sn'de olayı görmek, Bluetooth'u kapatıp yedek çıkışı duymak, 3 günlük gölge karnesi, yedekten geri yükleme ve yeniden başlatma provası |

---

## 14. Kabul kriterleri ve ölçüm yöntemi (hedef sayılar §4.8'den; her biri NASIL ölçülecek; mevcut ölçüm altyapısı)

Mevcut ölçüm altyapısı: `tests/hiz_kiyas` (hız; elle koşulur, AUDIT-OLCUM §1), inceleme işaretleri
(`olaylar_web.py:198`), rapor kırılımında yanlış alarm oranı (`rapor.py:127`), gölge mod
(`sema/002`), `tests/nesne_kiyas` (doğruluk takımı için yöntem şablonu). Eklenecekler: işlenen fps
ve `isle()` sayaçları (F2), `analysis_hours` (F2), `alert_deliveries.frame_to_start_ms` (F4),
`tests/dogruluk_kiyas` (F3/F5), `egitim/degerlendirme.py` (F3).

| Ölçüt | §4.8 hedefi | Bu tasarımdaki hedef / koşul | Nasıl ölçülecek | Bugün |
|---|---|---|---|---|
| `person` recall @IoU 0,5 | ≥ 0,95 | Aynı | `tests/dogruluk_kiyas`: KVKK dayanaklı etiketli saha karelerinde gerçek `Tespitci`; kutu etiketlemeyi kim yapacağı S11 | Ölçülmedi |
| `forklift`, `truck` mAP50 | ≥ 0,90 | forklift: ince ayarlı model gelince; truck: bugün de ölçülebilir ama car/bus'la birleşik | Aynı takım, sınıf başına | Ölçülmedi; forklift sınıfı yok |
| `PPE_NO_HELMET` precision / recall | ≥ 0,90 / ≥ 0,85 | Precision ≥ 0,90 **kabul kapısı**; recall raporlanır, taahhüt edilmez (E10, docs/04 §8.1) | Precision: gölge modda ≥3 gün, incelenmemiş olay kalmadan ve en az `KKD_KAPI_EN_AZ_OLAY` incelenmiş olayla, model sürümü başına (§5.7). Recall: etiketli test gününde elle sayım + HTML rapor | Ölçülemez (model yok) |
| `PPE_NO_VEST` precision / recall | ≥ 0,90 / ≥ 0,85 | Aynı | Aynı | Ölçülemez |
| Uçtan uca gecikme (kare → ses) | ≤ 500 ms uçta, ≤ 1 s sunucuda | Hedef donanıma koşullu (E13). Yazılım kısmı ayrı raporlanır | Yazılım: `frame_to_start_ms` p50/p90 (F4). Akustik: saha telefon videosu, kare sayımı (§7.10) | Yalnız tespit adımı ölçüldü: `tiny` p90 121–138 ms, `s` p90 473–496 ms (4 kamera, CPU) |
| Kamera başına işleme hızı | ≥ 10 fps | **6 fps** (E14, docs/05 bütçesi) | `/saglik` `islenen_fps` + hedef donanımda `tests/hiz_kiyas` | Bütçe `tiny` ile %100, `s` ile %40; işlenen fps bugün ölçülmüyor |
| Yanlış alarm | ≤ 2 / saat / kamera | Aynı; payda "analiz edilen saat" (kopukluk ve model yokluğu hariç) | `false_alarm` işaretli ihlal ÷ `analysis_hours.analyzed_s`, **yalnız inceleme kapsamı tam olan kamera × gün dilimlerinde** (o dilimin her ihlali "İncelendi" ya da "Yanlış alarm" işaretli). Payda olay değil saat olduğu için, işaretlenmemiş olaylar paydan düşerse oran yapay olarak düşer ve hedef "karşılandı" görünürdü (önceki sürümdeki "işaretlenmemiş olay paydaya ve paya girmez" cümlesi bu yüzden yanlıştı). Kapsama eksik dilimde hücrede "ölçülemedi" ve kapsama % yazar; gölge moddaki olaylar ayrı gösterilir | Yalnız işaretlilerde oran var (`rapor.py:127-150`), saatlik yok |
| Çalışma süresi | ≥ %99,5 / ay | Aynı | `analysis_hours` kapsaması + `CAMERA_DOWN.resolved_at − occurred_at` toplamı + `SYSTEM_STARTED/STOPPED` aralıkları | Geçmiş tutulmuyor |
| Uyarı garantisi (§4.6) | Her güvenlik olayı ≥1 sağlıklı kanala | Aynı, önemden bağımsız; yalnız sesli/uzak kanallar sayılır (ekran sayılmaz, K21) | `alert_deliveries`'te gölgede olmayan olay başına en az bir sesli/uzak `ok`; `ALERT_UNDELIVERED` sayısı | Kaydı yok |
| Kanal kopukluğu algılama (§4.6) | 30 sn'de olay | Aynı; "bilinmiyor" hariç | Sahte saatli birim testi + sahada hoparlörü kapatma | Periyodik yoklama yok |
| Kamera kopukluğu (§4.5) | 10 sn'de olay | Aynı (S18) | Birim testi + sahada kablo çekme | 60 sn |

Hedef tutmazsa gerçek sayı, nedeni ve sonraki adım yazılır (GÖREV §4.8); sayı ölçülmeden
"karşılandı" yazılmaz.

---

## 15. Riskler

| # | Risk | Etki | Hafifletme |
|---|---|---|---|
| 1 | CPU bütçesinde pay yok: `tiny` 4 × 6 fps'te %100, p90 121–138 ms; KKD sınıflandırıcısı, bulanıklık ve dağıtıcı eklenince aşılabilir; KKD maliyeti ölçülmedi | İşlenen fps düşer, gecikme artar | ORT 1.30 (~%25, yerel ölçüm); `KKD_KARE_ARALIGI`; `ANALYSIS_DEGRADED` görünür kılar; GPU kararı ölçüme bağlı |
| 2 | GPU yolu bugün teslim edilemiyor; iki ORT paketi aynı ortamda CUDA'yı sessizce kaybeder; 1.27+ CUDA 13 ister | Fabrika `s` modeliyle bütçeyi karşılayamaz | Ayrı imaj, tek paket kuralı, açılış uyarısı, duman testi |
| 3 | Ticari kullanıma açık, lisansı doğrulanmış KKD seti yok; Rev.02 teyit edilmedi | Faz 3 takvimi belirsiz; model gelene kadar PPE olayı yok | Faz 4 model beklenirken başlar (K32); kapı ve politika önce |
| 4 | Lisans: COCO/Flickr kökenli hazır ağırlıklar ve olası ImageNet ön eğitimi için hukuki görüş yok | Ticari teslimat riski | S20; kanıt dosyası; "kullanılamaz" listesi kesin |
| 5 | 007 `zones`'u yeniden kuruyor; FK denetimi COMMIT'ten sonra | Bölge kuralları silinebilir | İşaret satırı + otomatik yedek + 006 verili göç testi; deneme veritabanında doğrulandı (§8.2) |
| 6 | Olay yaşam döngüsü olay ve anons sayısını değiştirir: uzun ihlal tek satır olur, anons hatırlatma olarak çalar | Raporlar ve alışkanlık değişir; "bozuldu" algısı | Senaryo takımı davranışı kilitler; operatöre önceden anlatılır (§13 2c) |
| 7 | Çıkış histerezisi yanlış ayarlanırsa olay hiç kapanmaz ya da erken kapanır | "Sürüyor" asılı kalır ya da çift olay | Açılış/kapanış kapatma; senaryo testleri; `bitis_s` kural başına |
| 8 | Takip hafızası uzatılınca iki kişinin izi karışabilir, KKD oylaması başka kişinin gözlemini alır | Yanlış alarm ya da kaçırma | Öneri 2 sn; kayıtlı videoda ID değişimi ve karışma sayılır (S14) |
| 9 | Başlatma eşiği kararı (S15): 0,28–0,35 güvenli insan bugün iz açamıyor | Kaçırılan insan (ayarlar.py:290-292 niyetine aykırı) ya da hizalanırsa sahte iz | Operatör kararı; kabul takımında iki ayar karşılaştırılır |
| 10 | 10 sn `CAMERA_DOWN` ve 30 sn `AUDIO_CHANNEL_DOWN` dalgalı ağda olay seli | Yorgunluk, güven kaybı | UP için 5 sn ve 2 ardışık True; tek açık olay; eşik `.env`'de (S18) |
| 11 | Kanal sağlığı yoklaması kendisi yanlış alarm üretebilir (`pactl`'in anlık okunamaması, `auto_null` sink, uykuya giren hoparlör — DOĞRULANMADI) | Sahte "koptu" | 30 sn eşik; None olay üretmez; hedef sunucuda sınanır |
| 12 | "Ok" teslim "duyuldu" değildir; A2DP uykudan uyanırken ilk sesi yutabilir (ölçülmedi) | Garanti kâğıt üstünde kalır | Saha ses testi; Bluetooth tek sesli kanal olamaz uyarısı |
| 13 | Windows ve kısmen macOS'ta ses kanalı sağlığı "bilinmiyor" | `uyari_garantisi` bu platformlarda hep `null` (gri); ekran garantiye sayılmadığı için "sağlandı" denemez | Dürüst gri rozet; sahada Linux + kablolu/IP hoparlör önerisi |
| 14 | Fabrika container'ında ses yolu yok (R36); varsayılan (A) (`pulseaudio-utils` + host ses soketi) imaj derlenmeden ve hedef sunucuda sınanmadan DOĞRULANMADI. S29 "hayır" (B1) derse Bluetooth hoparlör fabrikada **hiç kullanılamaz**: operatörün doğrudan isteği varsayılan Docker dağıtımında karşılanmaz | Sesli uyarı yok ya da yalnız IP hoparlör | v2 bunu 30 sn'de görünür kılar (`AUDIO_CHANNEL_DOWN`, `sesli_kanal_yok`); S29; IP hoparlör yolu; Ç35'te açıkça yazılı |
| 15 | Bluetooth container'da: host ses soketi, aynı UID, ekransız WirePlumber ayarı (bekçi yazılırsa host D-Bus); paket adları DOĞRULANMADI. Bluez sink adı yeniden bağlanmada profil sonekiyle değişebilir (DOĞRULANMADI) | Kurulum karmaşık; sahte "koptu" | Sink adres deseniyle eşlenir; bekçi yalnız S9/S29 gerektirirse; IP hoparlör alternatifi; systemd/host yalnız operatör CLAUDE.md §4'ü değiştirirse |
| 16 | Bekçinin yanlış alarmı (model indirme, uzun bakım) | Gereksiz yeniden başlatma | Açılış evresinde devre dışı; eşik okuma zaman aşımından uzun; varsayılan tepki "uyar"; masaüstünde asla çıkış yok |
| 17 | Kalıcılık tek analiz iş parçacığında (R11); olay güncellemeleri yazım sayısını artırır | Bütün kameralar kısa süre kör | F2 sayaçları ölçer; yazıcı kuyruğu F5'te koşullu |
| 18 | Yüz bulanıklaştırma yanlış yere uygulanırsa KKD kanıtını bozar ya da yüzü kaçırır | Ölçüm ya da KVKK açığı | Yalnız dışa aktarım ve KKD dışı kanıt; 50 örnek ölçümü |
| 19 | KKD toplamanın kapatılması mevcut kurulumda veri akışını durdurur | "Bozuldu" algısı | S10'da önceden onay; ekranda açık satır |
| 20 | Forklift sınıfı yok; car/truck ayrılınca forklift mesafe kuralından kaçabilir | Güvenlik gerilemesi | Ayrım saha recall ölçümünden sonra; araç grubunun tamamı mesafe kuralında kalır (§12.3) |
| 21 | ORT 1.19.2 kalırsa CVE-2026-14647 açık ve Python 3.13+ kurulum kırılır; yükseltilirse Intel Mac geliştirmesi kırılır | Güvenlik ya da geliştirme ortamı | S19; ortam işaretçisi |
| 22 | supervision sabiti gevşetilirse (0.31) `sv.ByteTrack` kalkar | Takip kırılır | `==0.25.1` korunur; docs/07 notu |
| 23 | Güvenlik düzeltmeleri (Host izin listesi, Origin, şifre alanı) ters vekil ve uzaktan erişim kurulumlarında beklenmedik 421/403 üretebilir; sunucunun LAN IP'si ya da Tailscale adı listeye yazılmazsa başka makineden sayfa açılmaz | Uzaktan erişim bozulur | `IZINLI_SUNUCU_ADLARI` Ayarlar'da; 421 sayfası hangi adın eksik olduğunu Türkçe söyler; docs/15 senaryoları ayrıca sınanır |
| 24 | Kapsam büyük: dört fazda ~50 dosya; K22 (kanal yapılandırmasının `speaker_zones`'a taşınması) tek başına 10 test dosyasında ~40 satırı etkiler | Operatör davranışı doğrulayamaz | Alt adımlar, 10 dosya sınırı, her adımda deneme talimatı; koşullu maddeler (Ç35) yalnız cevap "evet" ise; K22 test geçişi 4a'nın ilk alt adımı |
| 25 | Kod adlarında belge ile kod arasındaki fark sürer (S26) | Kafa karışıklığı | Tek kural operatör kararıyla CLAUDE.md'ye yazılır |
| 26 | Tarayıcı `speechSynthesis` Türkçe sesi istemci işletim sistemine bağlı, çevrimdışı DOĞRULANMADI | Ekranın sesli kısmı çalışmayabilir | R41 çipi; WAV öncelikli |
| 27 | Sentetik senaryo takımı gerçek video davranışını kapsamaz; saha videosu KVKK yüzünden depoya giremez | Regresyon kör noktası | Kayıtlı video aracı pytest dışında, veri depo dışında |
| 28 | §4.8 hedefleri hiç ölçülmedi; tutmama olasılığı yüksek | Müşteri beklentisi | docs/00'ın koşullu performans ifadesi; ölçülmeden yazılmaz |
| 29 | Sesli/uzak kanal tanımlı değilken (yeni kurulum, `ANONS=null`'dan aktarım) her ihlal `ALERT_UNDELIVERED` adayı olur | Olay listesinde sistem olayı birikir | `ULASMAYAN_UYARI_ARALIGI_SN` hız sınırı; kalıcı `sesli_kanal_yok` satırı; kurulum listesinde kırmızı madde |
| 30 | Kapı ve eşik anahtarları (`KKD_KAPI_*`, `ANALIZ_*`) Ayarlar sayfasını büyütür | Operatörün anlamadığı ayar | Ayarlar gruplar hâlinde, her satırda Türkçe açıklama ve "öneri" etiketi; belgelenmiş sabitler (Ç36) Ayarlar'a girmez |
| 31 | Webhook (S4) kodlanmazsa ekran başında kimse yokken sistem olayları dışarı çıkmaz | `CAMERA_DOWN`, `ANALYSIS_STALLED` saatlerce fark edilmeyebilir | Kontrol Paneli ve sistem şeridi kırmızı; docs/07 satırı; S4 cevabı Faz 4'ten önce |

---

## 16. Açık sorular (operatöre; §8 + bu turda çıkanlar; her soruya "neden önemli" ve "varsayılan seçenek")

"Varsayılan" = operatör cevap vermezse tasarımın uygulayacağı seçenek. "Gerektiği an" = cevap
en geç ne zaman gerekir. Ç35 gereği "koşullu" işaretli maddeler cevap "evet" olmadıkça **kodlanmaz**,
docs/07'ye satır olur.

**Karar kaydı.**

- **Faz 1 onayı:** "Faz 2 öncesi" soruların (S10, S18, S19, S22, S25, S26, S30, S36)
  varsayılanları kabul edildi. Faz 2, S14, S17 ve S24'ü varsayılanlarıyla kodladı.
- **23.09.2026:** operatör Faz 3 ve Faz 4 sorularının varsayılanlarını kabul etti (S2, S3, S4,
  S8, S9, S11, S12, S16, S21, S23, S28, S29, S31, S32, S33, S34). Bu yüzden koşullu maddeler
  kodlanmaz: webhook, dakika sınırı/birleştirme, dışlama kipi, BT bekçisi, uygulama içi
  eşleştirme, KKD uyum istatistiği.
- **S20** o listede operatöre gösterilmedi. Kabul edilmiş sayılmaz. Ürün kodunu etkilemez: eğitim
  ürün dışıdır (S31). Cevap gelene kadar hukuk görüşü olmadan yeni ön eğitimli ağırlık ya da
  kamu veri seti kullanılmaz.
- **Açık:** S1, S5, S6, S7, S13, S15 (kayıtlı saha videosu gerekir), S20, S27, S35.

| # | GÖREV | Soru | Neden önemli | Varsayılan seçenek | Gerektiği an |
|---|---|---|---|---|---|
| S1 | §8-1 | Fabrika sunucusunun kesin donanımı nedir (GPU modeli, sürücünün CUDA 12 mi 13 mü desteklediği, çekirdek sayısı, VNNI, Ubuntu sürümü)? Kurulum Docker mı, systemd mi, paketli masaüstü mü? | GPU imajını, ORT sürümünü (GPU imajı pratikte ORT ≥ 1.21 ister, `preload_dlls`), ses/Bluetooth yolunu, bekçinin tepkisini, systemd bildiriminin yazılıp yazılmayacağını ve §4.8 gecikme hedefinin tutup tutmayacağını belirler | Ubuntu + Docker tek container (CLAUDE.md §4); GPU doğrulanana kadar `yolox_tiny` + CPU; systemd bildirimi (koşullu) yazılmaz | Faz 5 (bekçi için Faz 2) |
| S2 | §8-2 | AGPL-3.0 lisanslı model kabul edilebilir mi? | Model seçimini ve lisans yükümlülüğünü belirler; RT-DETR (Paddle) yalnız YOLOX §4.8'i tutmazsa ölçülür (Ç42) | Hayır; YOLOX (Apache-2.0, ADR-002) | Faz 3 |
| S3 | §8-3 | Hangi alanlar KKD'den muaf? Forklift/tır kabinindeki sürücüye baret şart mı? KKD yalnız çizilen bölgede mi, muaf alanlar dışında her yerde mi (dışlama kipi)? docs/04 §5.3'teki 10 politika sorusunu kim, ne zaman cevaplayacak? | Etiketleme ve kural davranışı bu cevaplara bağlı; yanlış politikayla etiketlenen veri baştan bozuktur (docs/08 R11). Dışlama kipi üç katmanda değişiklik ister (§5.5) | Sürücü muaf; kapsam = çizilen KKD bölgesi, `ppe_exempt` o bölgeden oyulur (kuralda ve örneklemede); dışlama kipi **koşullu**, kodlanmaz | Faz 3 |
| S4 | §8-4 | Sesli uyarının yanında hangi kanallar isteniyor, kim alacak (İSG uzmanı, vardiya şefi)? Ekran başında 7x24 biri var mı? Webhook'u alacak bir sistem var mı, imzayı doğrulayabilir mi? Yeni kurulumda kablolu ses (`local_audio`) kendiliğinden varsayılan kanal olsun mu (Ç39)? | Ekransız kurulumda sistem olayları ancak webhook ile dışarı çıkar; garanti yalnız sesli/uzak kanallara dayanır (K21) | Ekran + ses kartı / IP hoparlör; bugünkü `.env ANONS` "Tüm fabrika" satırına aktarılır; yeni kurulumda sesli kanal kendiliğinden kurulmaz, `sesli_kanal_yok` kırmızı görünür; webhook **koşullu**, kodlanmaz | Faz 4 |
| S5 | §8-5 | Olay, fotoğraf ve KKD kırpığı kaç gün saklanacak? KVKK sorumlusu (veri sorumlusu) kim? Dondurma yetkisi kimde? Roller ve olay klibi gerekli mi? | KVKK'da sabit gün yok; süreyi müşteri ve avukat gerekçelendirmeli; klip ve roller ayrı parçalardır | 180/90/30/90 gün değişmez; tek şifre + erişim günlüğü; klip yok; dondurma yönetici şifresi sahibinde | Faz 5 |
| S6 | §8-6 | Kamera sayısı ve yerleşimi kesin mi, gece ışık koşulu nasıl? Görüş alanında mahremiyet beklentisi olan alan var mı? RTSP akışlarında ses kanalı var mı? Kamera ağı ayrı VLAN'da mı? | Bütçe, KKD piksel boyu, KVKK levhası, "ses işlenmez" beyanı ve ağ bölümlendirmesi belgesi buna bağlı | 3–4 kamera, 6 fps; ses işlenmez; ağ belgesi ağ ekibiyle doldurulur | Faz 2 (bütçe), Faz 5 |
| S7 | §8-7 | Zemin kalibrasyonu (4 nokta) ve şeritle kontrol ölçümü sahada yapılabilir mi? | En kritik kural (yakınlık) ve hız kuralı kalibrasyonsuz pasif kalır; kontrol ölçümü metre iddiasının dayanağıdır | Kalibrasyonsuz kamerada iki kural pasif ve `kritik_kural_pasif` kırmızı; piksel sezgisi yok; doğrulanmamış kalibrasyonda metre "≈"; kontrol ölçümü **koşullu**, kodlanmaz | Faz 2 |
| S8 | E2 | Uygulama içinde Bluetooth tara/eşleştir ekranı isteniyor mu, yoksa OS'ta eşleştirme yeterli mi? | docs/14'ün bilinçli kararını geri almak demek; PIN'li hoparlör ve Windows'ta tam otomasyon zaten mümkün değil | OS'ta eşleştirme; kopma algılanır; yeniden bağlanma bekçisi S9'a bağlı | Faz 4 |
| S9 | — | Bluetooth hoparlörün markası, modeli, adedi? PIN istiyor mu? **Kapatılıp açılınca kendisi bağlanıyor mu?** Bölüm başına bir hoparlör mü? Ses seviyesini sistemin yönetmesi gerekiyor mu? | Yeniden bağlanma bekçisinin yazılıp yazılmayacağı bu cevaba bağlı (hoparlör kendiliğinden bağlanıyorsa bekçi gereksiz parça); ses seviyesi docs/14 §8'le çelişir | Bölüm başına en çok bir hoparlör, `trust` yapılmış; ses seviyesi yönetilmez; bekçi **yazılmaz**, sahada kendiliğinden bağlanmadığı görülürse (ve S29 izin verirse) yazılır | Faz 4 |
| S10 | E9 | Rev.02 ek protokolü imzalandı mı? KKD veri toplama kapısının başlangıç değeri "kapalı" olsun mu? | Bugün toplama ön koşulsuz açık; kapatmak mevcut kurulumda davranış değişikliğidir | Kapalı (007 `ppe_collection_gate` = 0); imza teyidiyle KKD sayfasından, yeniden başlatmadan açılır | **Faz 2 öncesi** |
| S11 | — | KKD kırpıklarını ve saha karelerindeki kutuları kim etiketleyecek? Eğitim GPU'su nereden gelecek? | Faz 3 takviminin ve §14 doğruluk ölçümünün ön koşulu; tespit kutusu kuralı docs/04 §5'e eklenir (Ç45) | İSG + NextGen etiketler; eğitim ürün dışında, GPU'lu ayrı makinede | Faz 3 |
| S12 | — | Sahada loader (kepçe) ve transpalet var mı? Binek araçların tırdan ayrılması gerekiyor mu? | Sınıf listesini ve veri ihtiyacını budar; loader için açık veri yok | Katalogda tanımlı, model üretmez; arayüz "Tır/Araç" | Faz 3 |
| S13 | — | Müşteride `/metrics` okuyacak bir Prometheus var mı? WebSocket/MQTT ya da olay/kamera için JSON REST API sözleşmede bağlayıcı mı? | Yoksa ölü uç ve fazladan parça; Prometheus çerezle oturum açamaz, Bearer anahtarı gerekir | Yok; metrik `/saglik` JSON'unda; SSE; REST API yok (Ç41); `/metrics` ve `METRIK_ANAHTARI` **koşullu** | Faz 5 |
| S14 | — | Kayıp iz hafızası (`TAKIP_HAFIZA_SN`) kaç saniye olsun? | Kısa → örtülmede yeni kimlik, tekrar uyarı; uzun → iz karışması | 2 sn; kayıtlı videoda ID değişimi sayılarak ayarlanır | Faz 2 |
| S15 | — | ByteTrack yeni iz başlatma eşiği insan eşiğiyle (0,28) hizalansın mı? Bugün 0,28–0,35 güvenli insan iz açamıyor; `ayarlar.py:290-292`'nin niyeti "kaçırılan insan daha riskli" | Hizalamak kaçırmayı azaltır ama sahte iz ve yanlış alarm artabilir | Bugünkü davranış (0,35) korunur; iki ayar kayıtlı videoda karşılaştırılıp sonuç size sunulur | Faz 2 sonu |
| S16 | — | KKD kararı docs/04 penceresiyle mi (≈12,5 sn, %75, en az 8 gözlem) yoksa §4.5'in 2 sn / %70'iyle mi verilsin? | İkincisi KKD'nin her karede çalışmasını (~5 kat yük) gerektirir; CPU'da pay yok | docs/04 penceresi | Faz 3 |
| S17 | — | Olay sürerken anons, kuralın bekleme süresi aralığıyla hatırlatılsın mı, yoksa olay başına tek anons mu? | Duyulur davranış değişir | Hatırlatır (bugünkü duyulur davranış); olay listesi dolmaz | Faz 2 |
| S18 | §4.5 | Kamera koptu olayı için 10 sn eşiği kabul mü? | Dalgalı RTSP'de olay seli üretebilir | 10 sn + UP için 5 sn kararlılık (ikisi de `.env`'de) | **Faz 2 öncesi** |
| S19 | — | ORT 1.19.2 → 1.30.0 yükseltmesi yapılsın mı? Geliştirmede hâlâ Intel Mac kullanılıyor mu? | CVE-2026-14647; ~%25 hız; Intel Mac 1.24+ tekerleği yok; 1.19.2'de `preload_dlls` yok (GPU imajı etkilenir); Python üst sınırı ORT'den bağımsız `<3.13` | 1.30.0; Intel Mac varsa 1.23.2 | **Faz 2 öncesi** |
| S20 | — | COCO/Flickr kökenli hazır ağırlıklar ve ImageNet ön eğitimli KKD omurgası ticari teslimatta kabul mü? "Koşullu" Roboflow setlerinin lisans satırlarını kim tarayıcıdan okuyup kaydedecek? CC BY atıfları kapalı üründe nerede gösterilecek? | Lisans riski; docs/16 uyarı 1 | Mevcut YOLOX ağırlıkları kullanılmaya devam eder; yeni ön eğitimli ağırlık ve kamu seti hukuk görüşünden sonra | Faz 3 |
| S21 | E3 | Türkçe anons WAV'larını kim kaydedecek? Üç yeni metnin (007) son hâli ne olacak? Sunucu TTS'i istenmediği varsayımı doğru mu? | WAV yoksa o olayda yalnız ekran + HTTP cihaz metni çalışır | Metinler taslak; WAV gelene kadar ekran + tarayıcı seslendirmesi | Faz 2 (metin), Faz 4 (WAV) |
| S22 | — | `zones.zone_type` CHECK kısıtı kaldırılsın mı (doğrulama yalnız kodda)? | Kaldırılmazsa her yeni bölge tipi CASCADE tuzaklı bir tablo yeniden kurması ister | Kaldır; kodların tek kaynağı `rules/tipler.py` | **Faz 2 öncesi** |
| S23 | §4.6 | Kanal başına dakikada en çok kaç sesli uyarı, hangi birleştirme penceresi? Kritik uyarılar sınırdan muaf mı? | Sel ile kaçırma arasında denge | Sınır ve birleştirme **koşullu**, kodlanmaz; bugünkü (kamera, mesaj) bastırması kanal başına korunur, critical açılış muaf | Faz 4 |
| S24 | — | Bekçi analizin takıldığını görünce Docker/systemd'de süreci kapatıp yeniden başlatsın mı, yalnız uyarsın mı? | Kendiliğinden toparlanma ile gereksiz yeniden başlatma arasında seçim | `uyar`; masaüstünde her durumda yalnız uyarı | Faz 2 |
| S25 | §4.5 | Yeni ek hazır kurallar (yaya yolunda araç, araç yolunda yaya) gölge modda mı doğsun? Yasak alan eşiği 2 sn mi kalsın, §4.5'in 1 sn'sine mi insin? | Yanlış alarm disiplini; mevcut hazır kuralların davranışı | Yeni ek hazır kurallar ve KKD gölgede doğar (`HazirKural.golge`); mevcutlar değişmez; yasak alan 2 sn | **Faz 2 öncesi** |
| S26 | GÖREV §0-6 | Yeni kod adları: komşularla tutarlı Türkçe mi, CLAUDE.md §8 ve GÖREV §0-6'daki İngilizce mi? | CLAUDE.md kendi içinde çelişik (§5 Türkçe dosya adları, §8 İngilizce isim kuralı); varsayılan öncelik kuralından bilerek sapar (Ç27) | Yeni Python dosyaları Türkçe; şema, olay kodu, ayar değeri, metrik İngilizce; karar CLAUDE.md §8'e yazılır | **Faz 2 öncesi** |
| S27 | §4.10 | Yüz bulanıklaştırma isteniyor mu; hangi yöntem (kutu üstü, YuNet yüz bandı)? | Kutu üstü baret kanıtını siler; YuNet uzak yüzü bulamaz | **Koşullu**, kodlanmaz; "evet" ise yalnız dışa aktarım ve KKD dışı kanıt | Faz 5 |
| S28 | GÖREV §5 | Faz 3'ün modeli beklenirken Faz 4 (uyarılar) başlasın mı? | KKD verisi haftalar sürebilir; bölge/mesafe olayları bugün de üretiliyor | Evet | Faz 3 sonu |
| S29 | — | Docker kurulumunda host'un ses soketinin (ve BT bekçisi yazılırsa `/run/dbus`'un) container'a bağlanmasına güvenlik politikası izin veriyor mu? | Container'da bugün ses yolu yok (R36); (B1) seçilirse Bluetooth hoparlör fabrikada kullanılamaz | **(A)** tek container + `pulseaudio-utils` + host ses soketi (CLAUDE.md §4 ile uyumlu; imaj derlenmedi, DOĞRULANMADI); systemd/host yalnız CLAUDE.md §4 değişikliğiyle | Faz 4 |
| S30 | §0-7; CLAUDE.md §2 | GÖREV §4'ün tamamı mı kodlansın, yoksa koşulsuz taban + cevabınıza bağlı maddeler mi (Ç35 listesi: webhook, sınır/birleştirme, yüz bulanıklaştırma, dışlama kipi, kontrol ölçümü, `/metrics`, systemd bildirimi, BT bekçisi, KKD uyum istatistikleri, uygulama içi eşleştirme)? | CLAUDE.md altın kuralı ile GÖREV'in "kapsamı sessizce daraltma" kuralı çelişir; kapalı tutulan kod da bakım yüküdür | Koşullu disiplin: her madde yalnız kendi sorusu "evet" ise | **Faz 2 öncesi** |
| S31 | docs/09 #7 | Model eğitimini kim yürütecek: uzmanın tek seferlik işi mi (runbook docs/04 §6, CLAUDE.md §5 güncellenir), yoksa sizin tek komutla çalıştıracağınız bir eğitim mi? | Eğitim PyTorch + YOLOX + GPU ister; docs/09 "bilgisayarda yalnız Python" der (Ç37) | Uzman işi, ürün dışı; ürün içinde tek komutla HTML değerlendirme raporu | Faz 3 |
| S32 | §7 | Sesli kanalların tümü tek bir Bluetooth hoparlörse sistem ne yapsın: çalıp her yerde kırmızı uyarı mı göstersin, yoksa başka bir sesli kanal eklenene kadar `hazir=false` mı dönsün? | GÖREV §7 yasağı; çalmayı reddetmek hiç ses çıkmaması demektir (Ç38) | Çalar + `tek_kanal_bluetooth` kırmızı (sistem şeridi, Kontrol Paneli, kurulum listesi) | Faz 4 |
| S33 | — | KKD anonsunu açma kapısı için en az kaç incelenmiş olay gereksin? | Tek incelenmiş olayla precision %100 çıkar ve kapı açılırdı | 30 (sıfır yanlış alarmda %95 güvenle hata ≤ %10, "üçler kuralı") | Faz 3 |
| S34 | §4.11 | KKD uyum istatistikleri (vardiya / gün / hafta) isteniyor mu? Vardiya saatleri nedir? | Uyum oranı her kararlı izin sayılmasını ister; kişi bazlı kırılım KVKK 8770'e aykırı (Ç40) | Bu turda yok; istenirse kamera/bölge bazında, kişi kırılımı olmadan, 008'de sayaçlarla | Faz 3 |
| S35 | §4.9 | Disk dolarken kanıt fotoğrafı ve KKD kırpığı yazımı hangi boş alanda dursun? | Disk dolarsa SQLite de yazamaz, olay kaydı durur | `DISK_DUR_GB` = 1 (öneri; `DISK_UYARI_GB` = 5'in altında) | Faz 5 |
| S36 | CLAUDE.md §7 | §6.2'deki "belgelenmiş sabitler" listesi kabul mü? CLAUDE.md §7'ye "iç mekanik sabitler gerekçesiyle belgelenerek kodda kalabilir" notu eklensin mi? | §7 "sabit kodlanmış eşik yok" der; hepsini `.env`'e taşımak Ayarlar'ı onlarca anlaşılmaz satıra çıkarır (Ç36) | Evet; olay üreten ya da arızanın görünme süresini belirleyen her eşik `.env`/kural parametresinde | **Faz 2 öncesi** |

---

## 17. Doğrulama izi

Bu düzeltme turuna üç mercekten **53 bulgu** geldi: CLAUDE.md uyumu 11 (2 high, 6 medium, 3 low),
kod tabanında uygulanabilirlik 22 (1 high, 8 medium, 13 low), gereksinim kapsamı ve güvenlik
mantığı 20 (3 high, 9 medium, 8 low). Altı "high" bulgunun altısı da düzeltildi: S29 varsayılanı
(Ç29, §7.6), Docker'da yazılamayan `.env` ve KKD kapısının SQLite'a taşınması (iki mercek aynı
sorunu buldu; K17, §5.8, R27), ekranın garantiden çıkarılması (K21, §7.4), varsayılan sink
totolojisi (§7.2), Host izin listesi (R8).

| Sonuç | Sayı | Not |
|---|---|---|
| Düzeltildi | 53 | Her biri koddan yeniden doğrulandı (dosya:satır bu belgenin ilgili bölümünde) |
| Tamamen reddedildi | 0 | — |
| Düzeltilip bir alt önerisi gerekçeyle reddedildi | 5 | `hold`/`purge_log`/`access_log`'un koşullu yapılması (yasal yükümlülük, kapalı özellik değil); başlıksız POST'un reddi (tarayıcı dışı istemci CSRF vektörü değil, testleri kırardı; Host izin listesi DNS rebinding'i zaten kapatır); critical olmayan anonsların olay anahtarıyla bastırılması (birleştirme kodlanmadıkça bugünkü duyulur davranışı bozar; asıl açık critical muafiyetle kapandı); `BT_YENIDEN_BAGLAN` varsayılanının `acik` yapılması (bekçi S9/S29'a koşullandı, anahtar kaldırıldı); ekran için görünür sayfa nabzı (ekran garantiden çıkarıldığı için gereksiz) |

Koddan yeniden doğrulananlar (bu turda, `390adf5` üzerinde): `docker-compose.yml:20`, `:24`;
`ayarlar.py:39-70`, `:211-215`, `:222-230`, `:233`, `:430-433`; `ayar_rotalari.py:18`;
`supervizor.py:252`, `:329-341`, `:453-469`, `:471-495`, `:497-507`, `:544-580`, `:582-638`,
`:642`; `motor.py:39-40`, `:43-53`, `:76-86`; `tipler.py:73-74`, `:80-97`; `kkd.py:25`, `:36-38`,
`:125-129`, `:163`; `boru_hatti.py:276-282`, `:302`; `ortak.py:11`, `:14`, `:35`, `:303-317`;
`kurallar.py:129`, `:233-259`; `kameralar.py:98`, `:453-465`, `:563-565`; `anons_web.py:159`
(announcement_messages'a yazan tek UPDATE); `anons.py:313-314`, `:338-349`; `ses_cihazlari.py:98-110`,
`:142-159`; `giris.py:85-96`, `:197`; `olaylar_web.py:98-142`; `rapor.py:127-150`;
`yazici.py:44-58`; `veritabani.py:85-139`; `dalsan_launcher.py:32`, `:990`; `canli.js:18`;
`ana_sayfa.html:123-124`; testler: `test_veritabani.py:39-63`, `:132-139`,
`test_komuta_kabugu.py:102-106`, `test_kamera_kaynagi.py:23-39`, `test_platform_uyumu.py:189-212`,
`test_anons_baglama.py:116`, `test_uyari_ve_anons.py:196`, `test_komuta_uyari_ve_anons.py:437-456`,
`test_saflik.py:33`, `:60`, `test_arayuz_surumu_ve_model_mesaji.py:40-50`, `conftest.py:92-136`;
`.env.example` 33 anahtar; `istemci.post` 25 test dosyasında; `.env ANONS*`'a bağlı 10 test dosyası.

Çalıştırılarak doğrulananlar (proje dışı geçici klasörde; depoda dosya değişmedi):

- `python3 -c "import hmac; hmac.compare_digest('şifre','şifre')"` →
  `TypeError comparing strings with non-ASCII characters is not supported` (R15).
- `.venv/bin/python -c "import onnxruntime as o; print(o.__version__, hasattr(o,'preload_dlls'))"`
  → `1.19.2 False`.
- 001–006 + 1 kamera, 3 bölge, 4 kural, 10 olay üstüne bu belgedeki 007–010 taslakları gerçek
  `veritabani.semayi_uygula()` ile: on sürüm kaydı; bölge 3, kural 4; kural bağı korundu;
  `foreign_key_check` boş; açık olay 0; mesaj 8; `ppe_collection_gate` `(1, 0)`; `event_code`
  NULL test satırı yazıldı; bölge silinince kural sayısı 3 (CASCADE); `EXPLAIN QUERY PLAN`
  `SEARCH events USING COVERING INDEX idx_events_resolved (resolved_at>?)` ve `(resolved_at=?)`.

Çalıştırılmayanlar: tam test paketi bu turda yeniden koşulmadı (belge değişikliği; §4.6'daki kırılma
listesi inceleme merceğinin depo kopyasındaki koşusuna ve koddan okumaya dayanır); Docker imajı
derlenmedi (R27 dizin bağlama, S29 (A) DOĞRULANMADI); hedef sunucuda ses sunucusunun varsayılanı
devretme davranışı ve bluez sink adının yeniden bağlanmada değişip değişmediği DOĞRULANMADI.
