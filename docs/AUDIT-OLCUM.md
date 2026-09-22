# AUDIT — Ölçümler ve çalıştırma denemesi

Faz 0 (keşif) denetiminin **ölçülen** yarısı. Keşfin okuma yarısı `docs/AUDIT.md`
dosyasındadır ve bu belgeye atıf yapar.

Buradaki hiçbir sayı tahmin değildir; her satır `tests/hiz_kiyas` takımının ya da
kayıt altına alınmış bir komutun çıktısıdır. Takım depoda durur, çünkü
"CPU yetersiz, GPU şart" cümlesi bir **donanım satın alma kararıdır** ve
tekrarlanabilir olmadan savunulamaz:

```bash
bash models/indir.sh
.venv/bin/python -m tests.hiz_kiyas
```

## 1. Ölçülen performans

Bu bölüm, dokümanlardaki performans iddialarını **ölçerek** sınar. Faz 0 kuralı gereği
hiçbir sayı tahmin değildir; her satır çalıştırılan bir betiğin çıktısıdır.

**Ölçüm ortamı — hedef donanım DEĞİLDİR:** 4 çekirdek Intel Xeon 2.1 GHz, 15 GB RAM,
**GPU yok**, Python 3.11.15, onnxruntime 1.19.2. Mevcut sağlayıcılar:
`['AzureExecutionProvider', 'CPUExecutionProvider']` — **CUDAExecutionProvider yok.**
Ölçüm sırasında arka planda başka işler çalışıyordu; sayılar üst sınır değil, büyüklük
mertebesi göstergesidir. Üç bağımsız koşuda sonuçlar %5 içinde tekrarlandı.

Ölçüm takımı `tests/hiz_kiyas/` altındadır; gerçek `app.analiz.tespit.Tespitci`
sınıfını kendi genel API'siyle çağırırlar: 1920×1080 BGR kare → `tespit_et()`.

### 1.1 Tek akış, kare başına uçtan uca (ön işleme + çıkarım + son işleme)

| Model | Girdi | `CIKARIM_IS_PARCACIGI` | Ortanca | p90 | Tek akış fps |
|---|---|---|---|---|---|
| `yolox_tiny.onnx` | 416 px | 0 (otomatik) | **33,5 ms** | 47,3 ms | 29,9 |
| `yolox_tiny.onnx` | 416 px | 3 | 34,5 ms | 40,3 ms | 29,0 |
| `yolox_tiny.onnx` | 416 px | 1 | 69,6 ms | 76,4 ms | 14,4 |
| `yolox_s.onnx` | 640 px | 0 (otomatik) | **91,3 ms** | 159,2 ms | 11,0 |
| `yolox_s.onnx` | 640 px | 3 | 113,7 ms | 142,2 ms | 8,8 |
| `yolox_s.onnx` | 640 px | 1 | 255,8 ms | 268,9 ms | 3,9 |

### 1.2 Dört kamera benzetimi (docs/05 §3 bütçesi: 4 × 6 fps = 24 çıkarım/sn)

Dört iş parçacığı, **tek paylaşılan `Tespitci`**, `tespit.py:163` kilidiyle sıralı
çıkarım; geciken kare düşürülür (gerçek boru hattı deseni). 12 saniye.

| Model | Bütçe karşılanma | Kamera başı fps | Ortanca gecikme (kilit dahil) | p90 |
|---|---|---|---|---|
| `yolox_tiny.onnx` | **%100** | 6,0 | 81–89 ms | 121–138 ms |
| `yolox_s.onnx` | **%40** | 2,4 | 394–399 ms | 473–496 ms |

### 1.3 Bu sayıların söyledikleri

1. **docs/05 §3'ün "CPU-only: kamera başına ~1-2 fps" iddiası kısmen yanlıştır.**
   `yolox_s` için ölçüm 2,4 fps ile iddiayı doğruluyor; `yolox_tiny` için ise sistem
   4 kamerada 6 fps bütçesini **tam karşılıyor**. Yani "CPU-only yetersiz" cümlesi
   modele bağlıdır ve belge bunu ayırmıyor.
2. **Ama `tiny` bütçeyi karşılarken makineyi de tüketiyor.** Bütçe %100 dolduğunda
   ortanca gecikme 33 ms'den 81 ms'ye, p90 121 ms'ye çıkıyor (kilit sıralaması).
   Geriye RTSP çözme, önizleme JPEG'i, web sunumu ve kural motoru için pay kalmıyor.
   Gerçek sistemde bu yapılandırma sınırdadır.
3. **Fabrika yapılandırması CPU'da çalışmaz.** `.env.example` fabrikaya `yolox_s`
   öneriyor; ölçüm bunun CPU'da bütçenin %40'ını verdiğini gösteriyor. GPU gerekçesi
   doğrudur — ama gerekçe `tiny`'den değil, `s`'den gelir.
4. **⚠️ GPU yolu bugün paketlenmiş hâliyle ÇALIŞAMAZ.** `backend/requirements.txt:14`
   yalnız CPU paketi olan `onnxruntime==1.19.2`'yi kurar; `onnxruntime-gpu` depoda
   **hiçbir yerde kurulmuyor** (yalnız `tespit.py:130` hata metninde ve
   `docs/06:273` sorun giderme satırında *adı geçiyor*). `Dockerfile:26` da aynı
   dosyayı kurar. Yani `docker-compose.yml:37`'nin talimatını harfiyen uygulayan
   bir operatör (GPU bloğunu açıp `CIKARIM_CIHAZI=cuda` yapan) GPU'yu satın almış
   olmasına rağmen CPU'da kalır.
   **Hafifletici:** sistem bunu sessizce yapmıyor — `tespit.py:124-132` sağlayıcı
   listesini kontrol edip `cihaz_uyarisi` üretiyor ve `supervizor.py:86` bunu ana
   sayfada Türkçe gösteriyor. Yani teşhis edilebilir bir hata, sessiz bir yavaşlık değil.
   **Gereken:** GPU imajında `onnxruntime-gpu` kurulmalı (CPU paketiyle aynı ortama
   kurulmamalı) ve CUDA/cuDNN sürüm eşleşmesi `docs/16` ile doğrulanmalı.
5. **`CIKARIM_IS_PARCACIGI` için ölçülmüş öneri:** 4 çekirdekte `0` (otomatik) en
   iyisi; `3`'e düşürmek `tiny`'de nötr, `s`'de **%25 yavaşlatıyor**; `1` her iki
   modelde de yıkıcı. `.env.example:31`'in "sunucu başka işler de yapıyorsa
   sınırlayın" tavsiyesi `s` modeli için ölçümle desteklenmiyor.
6. **§4.8'in "kare → ses ≤ 500 ms" hedefi açısından:** yalnız tespit adımı `tiny` ile
   p90'da 121–138 ms yiyor; `s` ile 473–496 ms, yani bütçeyi **tek başına** doldurur.
   Anons gecikmesi (A2DP 100–250 ms) üstüne binince `s` + CPU + Bluetooth birleşimi
   hedefi karşılayamaz.

## 2. Çalıştırma denemesi

Faz 0'ın "sistem gerçekten çalışıyor mu" sorusu, testlerden ayrı olarak sistemi
**ayağa kaldırarak** sınandı: `uvicorn app.main:app --port 8099`, `.env.example`
kopyası, `yolox_tiny.onnx`.

### 2.1 Açılış — temiz

Günlük **JSON yapısaldır** (§4.9'un "JSON yapısal günlük" isteği zaten karşılanıyor):

```
{"ts":"...","level":"INFO","bilesen":"sistem","mesaj":"Sistem hazır."}
{"ts":"...","level":"INFO","bilesen":"tespit","mesaj":"NextGen AI Hızlı yüklendi (girdi 416px, cihaz: cpu, ...)"}
{"ts":"...","level":"INFO","bilesen":"supervizor","mesaj":"Analiz süpervizörü başladı."}
{"ts":"...","level":"INFO","bilesen":"supervizor","mesaj":"Konfigürasyon değişti — yeniden yükleniyor (restart yok)."}
{"ts":"...","level":"INFO","bilesen":"supervizor","mesaj":"Bakım: ... boş disk 27.4 GB"}
```

Şema uygulandı, model yüklendi, süpervizör ve bakım çalıştı, sıcak yeniden yükleme
(§4.9 "yapılandırma sıcak yükleme") gözlendi.

### 2.2 Uçlar

14 sayfanın tamamı 200 döndü: `/`, `/kameralar`, `/kurallar`, `/olaylar`, `/anons`,
`/kkd`, `/videolar`, `/nesneler`, `/komuta`, `/komuta/saglik`, `/komuta/anons`,
`/komuta/uyari`, `/komuta/rapor`, `/saglik`.

`/saglik` gövdesi: `{"durum":"calisiyor","analiz":true,"model":"hazir"}`
→ §4.9'un `/healthz` isteği için **yeni uç gerekmez**, mevcut `/saglik` genişletilir.

### 2.3 Anons ve Bluetooth — görev tanımı §4.6'nın varsaydığından ÇOK daha fazlası var

Görev tanımı "Bluetooth hoparlöre bağlanma seçeneği ekle" derken sıfırdan bir kanal
varsayıyordu. Kodda **zaten** şunlar var:

| §4.6 gereksinimi | Bugünkü karşılığı | Durum |
|---|---|---|
| `AlertChannel {send, health, name}` | `NullAnonscu` · `SesKartiAnonscu` · `HttpAnonscu`, ortak `cal(anahtar, metin, ses_dosyasi)` + `ad` özelliği (`anons.py:46,103,224`) | kısmi — `health()` yok |
| `AlertDispatcher` | `AnonsYoneticisi` (`anons.py:275`): bölge seçimi, cooldown yazımı | kısmi |
| Hoparlör bölgeleri | `hoparlorler.py` + `sema/002_*.sql`, `bolge_sec()` (`anons.py:245`) | var |
| Tekrar bastırma | `ANONS_BEKLEME_SN=30`, `_son_anonsu_yaz()` | var |
| Bluetooth cihaz listeleme | `ses_cihazlari.py`: Linux `pactl` → `aplay -L` yedeği; Mac `system_profiler`; Windows PowerShell | var |
| Bluetooth ayırt etme | `_bluetooth_mu()` (`ses_cihazlari.py:113`) ad izleriyle: `bluez`, `bluetooth`, `airpods`, `jbl`, `soundlink`, `bose` | var ama **sezgisel** |
| Kanal sağlığı | `cihaz_bagli_mi()` (`ses_cihazlari.py:98`) — **üç durumlu**: bağlı / değil / bilinmiyor | var ama **yalnız sayfa açılınca** |
| Türkçe seslendirme | `uyari.js:71-76` `speechSynthesis`, `lang="tr-TR"` — **tarayıcıda** | var |
| Test sesi düğmesi | `POST /anons/test-sesi`; `ANONS≠ses_karti` iken 400 + anlaşılır Türkçe hata | var |

**Eksik olanlar (gerçek boşluk):** uygulama içi eşleştirme (docs/14 §2.1.1 bilerek
yapmadı), otomatik yeniden bağlanma, **periyodik** sağlık yoklaması ve
`AUDIO_CHANNEL_DOWN` olayı, kanal öncelik kuyruğu ve birleştirme, aynı anda birden
çok kanal (bugün `.env` ile TEK yol seçilir), ses seviyesi (docs/14 §8 bilerek yok),
gecikme ölçümü.

**Doğrulandı:** `cihaz_bagli_mi` yalnız `anons_web.py:81`'de, yani sayfa render
edilirken çağrılıyor. docs/14 bunu zaten dürüstçe söylüyor ("uyarıyı görmek için
birinin ekrana bakması gerekir"). §4.6'nın "en az bir sağlıklı kanala ulaşma
garantisi" için asıl eksik budur.

**Sunucu tarafı TTS neden gereksiz olabilir:** docs/14 §8 sunucuda TTS'i bilerek
dışarıda bırakmış; gerekçesi artık daha güçlü, çünkü tarayıcı katmanı Türkçe
seslendirmeyi zaten yapıyor. Görev tanımı §4.6'nın piper/espeak-ng önerisi bu ışıkta
yeniden değerlendirilmeli (EN AZ PARÇA).

### 2.4 Güvenlik notu

`grep -rn "shell=True" backend/ masaustu/ paketleme/` → **boş**. Ses cihazı ve anons
yolları `subprocess.run` ile liste argüman kullanıyor, 5 sn zaman aşımlı
(`ses_cihazlari.py:118-131`). Görev tanımının §4.10 "komut enjeksiyonu" endişesi bu kod
tabanı için **dayanaksızdır**.
