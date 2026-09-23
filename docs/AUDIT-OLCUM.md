# AUDIT — Ölçümler ve çalıştırma denemesi

Faz 0 (keşif) denetiminin **ölçülen** yarısı. Keşfin okuma yarısı `docs/AUDIT.md`
dosyasındadır ve bu belgeye atıf yapar.

Buradaki sayılar ya `tests/hiz_kiyas` takımının ya da bu belgede komutuyla birlikte
kayda geçen bir çalıştırmanın çıktısıdır. Ölçülmeyip başka yerden alınan tek sayı
(A2DP gecikmesi, §1.3 madde 6) orada ayrıca işaretlenmiştir. Takım depoda durur, çünkü
"CPU yetersiz, GPU şart" cümlesi bir **donanım satın alma kararıdır** ve
tekrarlanabilir olmadan savunulamaz:

```bash
bash models/indir.sh
.venv/bin/python -m tests.hiz_kiyas
```

## 1. Ölçülen performans

Bu bölüm, dokümanlardaki performans iddialarını **ölçerek** sınar.

**Ölçüm ortamı — hedef donanım DEĞİLDİR:** 4 çekirdek Intel Xeon 2.1 GHz, 15 GB RAM,
**GPU yok**, Python 3.11.15, onnxruntime 1.19.2. Mevcut sağlayıcılar:
`['AzureExecutionProvider', 'CPUExecutionProvider']` — **CUDAExecutionProvider yok.**
Ölçüm sırasında arka planda başka işler çalışıyordu; sayılar üst sınır değil, büyüklük
mertebesi göstergesidir. Tekrarlanabilirlik aşağıdaki tabloda ham hâliyle durur: koşular
arası fark `yolox_s`'de %5,4, `yolox_tiny`'de **%13,9**'dur. Üçüncü koşu 25 değil 8 turla
yapıldığı için örneklemi küçüktür; farkın bir kısmı buradan gelir.

| Tek akış ortancası (otomatik iş parçacığı) | 1. koşu (25 tur) | 2. koşu (25 tur) | 3. koşu (8 tur) | Fark |
|---|---|---|---|---|
| `yolox_tiny.onnx` | 34,4 ms | 33,5 ms | 30,2 ms | %13,9 |
| `yolox_s.onnx` | 86,6 ms | 91,3 ms | 89,3 ms | %5,4 |

Dört kamera benzetimi iki koşuda yapıldı (üçüncü koşu yalnız `--tek` idi); §1.2'deki
aralıklar bu iki koşunun uçlarıdır.

Ölçüm takımı `tests/hiz_kiyas/` altındadır; gerçek `app.analiz.tespit.Tespitci`
sınıfını kendi genel API'siyle çağırırlar: 1920×1080 BGR kare → `tespit_et()`.

### 1.1 Tek akış, kare başına uçtan uca (ön işleme + çıkarım + son işleme)

Aşağıdaki tablo 2. koşudur (25 tur).

| Model | Girdi | `CIKARIM_IS_PARCACIGI` | Ortanca | p90 | Tek akış fps |
|---|---|---|---|---|---|
| `yolox_tiny.onnx` | 416 px | 0 (otomatik) | **33,5 ms** | 47,3 ms | 29,9 |
| `yolox_tiny.onnx` | 416 px | 3 | 34,5 ms | 40,3 ms | 29,0 |
| `yolox_tiny.onnx` | 416 px | 1 | 69,6 ms | 76,4 ms | 14,4 |
| `yolox_s.onnx` | 640 px | 0 (otomatik) | **91,3 ms** | 159,2 ms | 11,0 |
| `yolox_s.onnx` | 640 px | 3 | 113,7 ms | 142,2 ms | 8,8 |
| `yolox_s.onnx` | 640 px | 1 | 255,8 ms | 268,9 ms | 3,9 |

### 1.2 Dört kamera benzetimi (docs/05 §3 bütçesi: 4 × 6 fps = 24 çıkarım/sn)

Dört iş parçacığı, **tek paylaşılan `Tespitci`**, `tespit.py:159` kilidiyle (`:175`'te alınır) sıralı
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
4. **⚠️ GPU yolu bugün paketlenmiş hâliyle ÇALIŞAMAZ.** `backend/requirements.txt:21`
   yalnız CPU paketi olan `onnxruntime==1.19.2`'yi kurar; `onnxruntime-gpu` depoda
   **hiçbir yerde kurulmuyor** (yalnız `tespit.py:130` hata metninde ve
   `docs/06:273` sorun giderme satırında *adı geçiyor*). `Dockerfile:18` de aynı
   dosyayı kurar. Yani `docker-compose.yml:37`'nin talimatını harfiyen uygulayan
   bir operatör (GPU bloğunu açıp `CIKARIM_CIHAZI=cuda` yapan) GPU'yu satın almış
   olmasına rağmen CPU'da kalır.
   **Hafifletici:** sistem bunu sessizce yapmıyor — `tespit.py:122-132` sağlayıcı
   listesini kontrol edip `cihaz_uyarisi` üretiyor ve `supervizor.py:86-87` ve `:274-276` bunu
   ana sayfaya taşıyıp Türkçe gösteriyor. Yani teşhis edilebilir bir hata, sessiz bir yavaşlık değil.
   **Gereken:** GPU imajında `onnxruntime-gpu` kurulmalı (CPU paketiyle aynı ortama
   kurulmamalı) ve CUDA/cuDNN sürüm eşleşmesi `docs/16` ile doğrulanmalı.
5. **`CIKARIM_IS_PARCACIGI` için ölçülmüş öneri:** 4 çekirdekte `0` (otomatik) en
   iyisi; `3`'e düşürmek `tiny`'de nötr, `s`'de **%25 yavaşlatıyor**; `1` her iki
   modelde de yıkıcı. `.env.example:37-40`'ın "sunucu başka işler de yapıyorsa
   sınırlayın" tavsiyesi `s` modeli için ölçümle desteklenmiyor.
6. **§4.8'in "kare → ses ≤ 500 ms" hedefi açısından:** yalnız tespit adımı `tiny` ile
   p90'da 121–138 ms yiyor; `s` ile 473–496 ms, yani bütçeyi **tek başına** doldurur.
   Bluetooth hoparlörün (A2DP) kendi gecikmesi buna eklenir. **Bu gecikme ÖLÇÜLMEDİ:**
   görev tanımındaki "100–250 ms" aralığı oradan alınmıştır ve `docs/16` §4 onu da
   DOĞRULANMADI olarak işaretler. Ölçülen kısım yalnız şudur: `s` + CPU birleşimi
   500 ms'lik bütçeyi tespit adımında tek başına doldurur; üstüne binecek her anons
   gecikmesi hedefi aşar.

## 2. Çalıştırma denemesi

Faz 0'ın "sistem gerçekten çalışıyor mu" sorusu, testlerden ayrı olarak sistemi
**ayağa kaldırarak** sınandı: `uvicorn app.main:app --port 8099`, `.env.example`
kopyası, `yolox_tiny.onnx`.

### 2.1 Açılış — temiz

Uygulamanın kendi günlüğü **JSON yapısaldır** (`loglama.py:84-101`):

```
{"ts":"...","level":"INFO","bilesen":"sistem","mesaj":"Sistem hazır."}
{"ts":"...","level":"INFO","bilesen":"tespit","mesaj":"NextGen AI Hızlı yüklendi (girdi 416px, cihaz: cpu, ...)"}
{"ts":"...","level":"INFO","bilesen":"supervizor","mesaj":"Analiz süpervizörü başladı."}
{"ts":"...","level":"INFO","bilesen":"supervizor","mesaj":"Konfigürasyon değişti — yeniden yükleniyor (restart yok)."}
{"ts":"...","level":"INFO","bilesen":"supervizor","mesaj":"Bakım: ... boş disk 27.4 GB"}
```

**Ama §4.9'un "JSON yapısal günlük" isteği yalnız kısmen karşılanıyor.** Aynı
çalıştırmada uvicorn'un kendi satırları düz metin çıktı ve `sistem.log`'a girmiyor:

```
INFO:     Started server process [8778]
INFO:     Uvicorn running on http://127.0.0.1:8099 (Press CTRL+C to quit)
INFO:     127.0.0.1:39344 - "GET /saglik HTTP/1.1" 200 OK
```

Şema uygulandı, model yüklendi, süpervizör ve bakım çalıştı, sıcak yeniden yükleme
(§4.9 "yapılandırma sıcak yükleme") gözlendi.

### 2.2 Uçlar

Komut (sunucu `127.0.0.1:8099`'da açıkken, her uç için):

```bash
curl -s -o /dev/null -w '%{http_code}' --max-time 20 "http://127.0.0.1:8099$u"
```

Ham çıktı:

```
/saglik              200
/                    200
/kameralar           200
/kurallar            200
/olaylar             200
/anons               200
/kkd                 200
/videolar            200
/komuta              200
/komuta/saglik       200
/komuta/anons        200
/komuta/uyari        200
/komuta/rapor        200
/komuta/nesneler     404
/nesneler            200
```

Denenen 15 adresin 14'ü 200 döndü. `/komuta/nesneler` için 404 bir hata değildir:
böyle bir rota yok, adres yanlış tahmin edilmişti; nesneler sayfası `/nesneler`'dedir
(`nesne_rotalari.py:37`). Bu deneme yalnız sayfaların açıldığını gösterir; içeriklerini
ve 72 rotanın tamamını sınamaz (rota envanteri `docs/AUDIT.md` §4.6'dadır).

`/saglik` gövdesi: `{"durum":"calisiyor","analiz":true,"model":"hazir"}`
→ §4.9'un `/healthz` isteği için **yeni uç gerekmez**, mevcut `/saglik` genişletilir.

### 2.3 Anons ve Bluetooth — görev tanımı §4.6'nın varsaydığından ÇOK daha fazlası var

Görev tanımı "Bluetooth hoparlöre bağlanma seçeneği ekle" derken sıfırdan bir kanal
varsayıyordu. Kodda **zaten** şunlar var:

| §4.6 gereksinimi | Bugünkü karşılığı | Durum |
|---|---|---|
| `AlertChannel {send, health, name}` | `NullAnonscu` · `SesKartiAnonscu` · `HttpAnonscu`, ortak `cal(anahtar, metin, ses_dosyasi)` + `ad` özelliği (`anons.py:46,103,224`) | kısmi — `health()` yok |
| `AlertDispatcher` | `AnonsYoneticisi` (`anons.py:275`): bölge seçimi ve tekrar bastırma | kısmi |
| Hoparlör bölgeleri | `hoparlorler.py` + `sema/002_*.sql`, `bolge_sec()` (`anons.py:245`) | var |
| Tekrar bastırma | `ANONS_BEKLEME_SN=30`; bastırmayı `Cooldown` yapar (`anons.py:289`, `duyur()` içinde `:313-314`). `_son_anonsu_yaz()` (`:368`) bastırmaz, yalnız ekrandaki "son anons" damgasını yazar | var |
| Bluetooth cihaz listeleme | `ses_cihazlari.py`: Linux `pactl` → `aplay -L` yedeği; Mac `system_profiler`; Windows PowerShell | var |
| Bluetooth ayırt etme | `_bluetooth_mu()` (`ses_cihazlari.py:113`) ad izleriyle: `bluez`, `bluetooth`, `airpods`, `jbl`, `soundlink`, `bose` | var ama **sezgisel** |
| Kanal sağlığı | `cihaz_bagli_mi()` (`ses_cihazlari.py:98`) — üç durumlu: bağlı / değil / bilinmiyor | **dar**: yalnız sayfa açılınca, yalnız Linux'ta ve yalnız açıkça bir cihaz seçildiyse anlamlı (aşağıya bakın) |
| Türkçe seslendirme | `uyari.js:71-76` `speechSynthesis`, `lang="tr-TR"` — **tarayıcıda** | var |
| Test sesi düğmesi | `POST /anons/test-sesi`; `ANONS≠ses_karti` iken 400 + anlaşılır Türkçe hata | var |

**Eksik olanlar (gerçek boşluk):** uygulama içi eşleştirme (docs/14 §2.1.1 bilerek
yapmadı), otomatik yeniden bağlanma, **periyodik** sağlık yoklaması ve
`AUDIO_CHANNEL_DOWN` olayı, kanal öncelik kuyruğu ve birleştirme, aynı anda birden
çok kanal (bugün `.env` ile TEK yol seçilir), ses seviyesi (docs/14 §8 bilerek yok),
gecikme ölçümü.

**Kanal sağlığı neden dar — üç kör nokta, üçü de koddan doğrulandı:**

1. **Yalnız sayfa açılınca.** `cihaz_bagli_mi` tek yerde çağrılıyor: `anons_web.py:81`,
   anons sayfası render edilirken. Periyodik yoklama yok. docs/14 bunu dürüstçe
   söylüyor ("uyarıyı görmek için birinin ekrana bakması gerekir").
2. **Varsayılan çıkışta hep "bağlı".** Cihaz seçilmemişse (`ANONS_SES_CIHAZI` boş,
   ki bu varsayılandır) fonksiyon koşulsuz `True` döner (`ses_cihazlari.py:105-106`).
   Varsayılan çıkış olarak kullanılan bir Bluetooth hoparlörün kopması görülmez.
3. **Mac ve Windows'ta çalınan cihaz denetlenen cihaz değil.** Çalıcılar (`afplay`,
   PowerShell `SoundPlayer`) cihaz adı almaz; ses her zaman işletim sisteminin
   varsayılan çıkışına gider (`anons.py:60-100`, `ses_cihazlari.py:68-74`). Oraya bir
   ad kaydedilse bile (`anons_web.py:86-102` değeri doğrulamaz), denetlenen o ad,
   çalınan ise varsayılan çıkıştır.

§4.6'nın "en az bir sağlıklı kanala ulaşma garantisi" için asıl eksik budur.

**Sunucu tarafı TTS neden gereksiz olabilir:** docs/14 §8 sunucuda TTS'i bilerek
dışarıda bırakmış; gerekçesi artık daha güçlü, çünkü tarayıcı katmanı Türkçe
seslendirmeyi zaten yapıyor. Görev tanımı §4.6'nın piper/espeak-ng önerisi bu ışıkta
yeniden değerlendirilmeli (EN AZ PARÇA).

### 2.4 Güvenlik notu

`grep -rn "shell=True" backend/ masaustu/ paketleme/` → **boş**. Alt süreç çağrıları
liste argüman kullanıyor. Zaman aşımları üç ayrı değerdir: cihaz listeleme 5 sn
(`ses_cihazlari.py:49`, `:123`), ses kartından çalma 20 sn (`anons.py:143`), HTTP
anons 5 sn (`anons.py:210`).

**Komut enjeksiyonu yüzeyi var ama hafifletilmiş; "yok" değil.** Windows'ta çalma komutu
bir PowerShell `-Command` metnidir ve ses dosyasının yolu bu metnin içine
yerleştirilir (`anons.py:72-83`). Yol arayüzden girilir. Kod tek tırnağı ikileyerek
metnin erken kapanmasını önler ve kendi yorumunda bunu açıkça "komut enjeksiyonu
yüzeyi" diye anar. Linux ve Mac yollarında dosya adı ayrı bir argümandır, yorumlanmaz.
Görev tanımı §4.10'un bu konudaki endişesi Linux fabrika sunucusu için geçersiz,
Windows geliştirme kurulumu için hafifletilmiş bir risk olarak geçerlidir.

## 3. Düzeltme kaydı

Bu belgenin ilk sürümü (`4a36997`) Faz 0 çürütme turunda yedi noktada yanlış ya da
fazla iddialı bulundu. Hepsi koddan yeniden doğrulanıp yukarıda düzeltildi:

| # | İlk sürümde | Doğrusu |
|---|---|---|
| 1 | Üç koşu "%5 içinde" | `tiny` %13,9, `s` %5,4; ham sayılar §1'de |
| 2 | Bütün sayılar ölçüldü | A2DP gecikmesi ölçülmedi, görev tanımından alındı |
| 3 | Günlük JSON, §4.9 karşılanıyor | Yalnız uygulama günlüğü JSON; uvicorn satırları düz metin |
| 4 | "14 sayfa 200", ham çıktı yok | Ham çıktı eklendi; 15 denemenin 14'ü 200, biri yanlış tahmin edilmiş adres |
| 5 | Tekrar bastırma `_son_anonsu_yaz()` | `Cooldown`; o fonksiyon yalnız damga yazar |
| 6 | Kanal sağlığı "üç durumlu, var" | Dar: yalnız sayfa açılınca, varsayılan çıkışta hep "bağlı", Mac/Windows'ta çalınan cihaz denetlenmez |
| 7 | Komut enjeksiyonu "dayanaksız", 5 sn zaman aşımı | Windows'ta hafifletilmiş bir yüzey var; zaman aşımları 5 / 20 / 5 sn |
| — | Satır atıfları | `requirements.txt:21`, `Dockerfile:18`, `tespit.py:159/:175`, `:122-132`, `.env.example:37-40` |

Ölçümün asıl sonuçları değişmedi: bütçe `tiny` ile %100, `s` ile %40; GPU paketi
hiçbir yerde kurulmuyor.
