# Nasıl Çalışır - Kurulum ve Çalıştırma Kılavuzu

Bu dosya üç projeyi birden anlatır ve **hangi ortamda neyin çalıştığını**
dürüstçe yazar. Yazılım bilmeden okunabilecek şekilde yazılmıştır.

| Proje | Ne yapar | Adres |
|---|---|---|
| **DALSAN-ISG** | Fabrika İSG sistemi: bölge ihlali, güvenli mesafe, KKD | `http://127.0.0.1:8080` |
| **OTOPARK-DEMO** | Kafe otoparkı: araç sayımı, renk, araçlar arası mesafe | `http://127.0.0.1:8090` |
| **LAFFOGATO** | Kafe barı: bardak sayımı (müşteri / barista) | `http://127.0.0.1:8100` |

Üçü birbirinden bağımsızdır. Aynı anda çalışabilirler; biri kapanırsa
diğerleri etkilenmez.

---

## 1. Sistem nasıl çalışır

Üç proje de aynı iskelet üzerine kuruludur:

```
Kamera (RTSP / USB / video dosyası)
        │  saniyede 3-6 kare örneklenir (hepsi değil - işlemci boğulmasın)
        ▼
   TESPİT       Görüntüde ne var? (insan, araç, bardak…)  → NextGen AI
        ▼
   TAKİP        Aynı nesne mi, yeni nesne mi? → her nesneye bir takip numarası
        ▼
   KARAR        Kural motoru: bölgede mi, kaç saniyedir, kaç metre uzakta,
                bardak hangi tarafta… (kare değil, TAKİP bazlı karar)
        ▼
   KAYIT        Olay + kanıt fotoğrafı → tek dosyalık veritabanı
        ▼
   EKRAN        İzleme ekranı (web sayfası); 1-2 saniyede bir kendini günceller
```

**Neden "takip bazlı karar":** tek bir karede yanılmak kolaydır (gölge, toz,
hareket bulanıklığı). Sistem bir nesneyi birkaç saniye izler, sonra karar
verir. Bu yüzden sayılar birkaç saniye gecikmeyle görünür - bu bir yavaşlık
değil, yanlış alarmı önleyen bilinçli bir tasarımdır.

**Karar verilemeyen durumlar "belirsiz" yazılır**, ihlal sayılmaz. Kanıtın
yokluğu, ihlalin varlığı değildir.

**Tek program:** Web sayfası ve analiz aynı program içinde çalışır. Başlatılacak
tek şey, bakılacak tek günlük vardır.

**Tek veri klasörü:** `veri/` - veritabanı, olay fotoğrafları, günlükler.
**Yedekleme = bu klasörü kopyalamak.**

---

## 2. Ne nerede çalışır (dürüst tablo)

| | Mac (çift tık) | Windows (çift tık) | Docker (Mac/Win) | Docker (Linux sunucu) |
|---|---|---|---|---|
| Sistemin kendisi, arayüz | ✅ | ✅ | ✅ | ✅ |
| Video dosyasıyla deneme | ✅ | ✅ | ✅ | ✅ |
| **IP kamera (RTSP)** | ✅ | ✅ | ✅ | ✅ |
| **Bilgisayarın kendi kamerası** | ❌ *(DALSAN yalnız RTSP ve video dosyası kabul eder)* | ❌ | ❌ | ❌ |
| **Ekran kartı (GPU) hızlandırma** | ❌ *(Mac'te CUDA yok)* | ❌ *(kurulum yalnız CPU paketini kurar)* | ❌ | ❌ *(imaj yalnız CPU paketini kurar; GPU için `onnxruntime-gpu`'lu ayrı imaj gerekir, henüz yok)* |
| Anons - ses kartı | ✅ | ✅ | ❌ | ⚠️ *(`docker-compose.ses.yml` ile; sunucuda henüz denenmedi)* |
| Anons - IP hoparlör (HTTP) | ✅ | ✅ | ✅ | ✅ |
| 7/24 kendiliğinden çalışma | ⚠️ pencere açık kalmalı | ✅ paketlenmiş uygulamada (`NextGen Detector.exe`), iki şartla: Windows otomatik oturum açmalı, BIOS elektrik gelince bilgisayarı açmalı (docs/06 §1.5). `Baslat-Windows.bat` ile ⚠️ pencere açık kalmalı | ✅ | ✅ |

**Özet karar:**
- **Geliştirme ve deneme** → Mac/Windows'ta çift tık. Docker gereksiz.
- **Kafe demoları (Laffogato'nun canlı kamerası)** → çift tık; Docker'da
  bilgisayar kamerası çalışmaz.
- **Fabrika kurulumu, ilk aşama** (operatör kararı 24.09.2026) → fabrikanın
  Windows bilgisayarında paketlenmiş uygulama, sunucusuz: program siz kapatana
  kadar açık kalır (`docs/06-OPERASYON.md` §1.5).
- **Fabrika sunucusu (7/24, GPU), sonraki aşama** → Linux sunucu + Docker;
  donanımı ve kurulum biçimi açık karar (`docs/17-V2-TASARIM.md` §16 S1).

---

## 3. Mac'te çalıştırma

1. [python.org](https://www.python.org/downloads/) → **Python 3.12** kur.
2. Proje klasöründeki **Baslat-Mac.command** dosyasına **çift tıkla**.
   Kontrol Paneli açılır. DALSAN'da ilk seferde **İlk Kurulumu Yap** gerekli
   paketleri kurar (birkaç dakika sürer); sonra **Sistemi Başlat**'a basılır.
3. İzleme ekranı kendiliğinden, adres çubuğu olmayan bir pencerede açılır.

İlk açılışta macOS "geliştirici doğrulanamadı" derse: **sağ tık → Aç → Aç**.

**Kamera izni (Laffogato):** bilgisayarın kamerasını ilk kullanışta macOS izin
sorar → **İzin Ver**. Sonradan değiştirmek için: Sistem Ayarları → Gizlilik ve
Güvenlik → Kamera.

**Pencereyi kapatmak sistemi durdurur.** Fabrika kurulumu bunun için değil:
ilk aşamada fabrikada Windows'taki paketlenmiş uygulama çalışır (§2 özet),
sunucu aşaması Docker içindir (aşağıya bakın).

---

## 4. Windows'ta çalıştırma

1. [python.org](https://www.python.org/downloads/) → **Python 3.12** kur.
   Kurulum ekranında **"Add Python to PATH"** kutusunu işaretle - en kritik adım.
2. **Baslat-Windows.bat** dosyasına **çift tıkla**.
   SmartScreen uyarısı çıkarsa: Daha fazla bilgi → Yine de çalıştır.
   Kontrol Paneli açılır. DALSAN'da ilk seferde **İlk Kurulumu Yap** gerekli
   paketleri kurar (birkaç dakika sürer); sonra **Sistemi Başlat**'a basılır.
3. İzleme ekranı kendiliğinden, adres çubuğu olmayan bir pencerede açılır.

Windows'a özel olarak halledilmiş şeyler:
- **Başlatıcı:** `py -3.12` ile (yoksa `py -3` ile) başlatılır. `where python`
  Windows 10/11'de Python kurulu olmasa bile başarılı olur (Microsoft Store
  takma adı yüzünden) ve Mağaza'yı açıp pencereyi kapatırdı.
- **Türkçe günlük:** Kontrol Paneli alt sürecin çıktısını UTF-8 okur. Aksi halde
  büyük Ş/Ğ harfleri Windows'un cp1254 kod sayfasında çözülemiyor ve günlük
  penceresi sessizce donuyordu.
- **Saat dilimi:** Windows saat dilimi veritabanıyla gelmez; `tzdata` paketi
  bağımlılıklara eklendi, saatler Türkiye saatinde doğru gösterilir.
- **Anons sesi:** `afplay`/`aplay` Windows'ta yoktur; Python'un kendi `winsound`
  modülü kullanılır. **Yalnızca .wav çalar** - sistem başka biçimi kabul etmez.
- **Türkçe klasör adı:** Kanıt ve KKD fotoğrafları `C:\Users\Gökhan\...` gibi
  yollara da yazılabilir (OpenCV'nin yol kodlaması atlanır).
- **Kamera:** Kaynak olarak yalnızca RTSP adresi veya video dosyası kullanılır;
  bilgisayarın kendi kamerası DALSAN kapsamında değildir.

---

## 5. Docker ile çalıştırma

Docker, **fabrika sunucusu için** düşünülmüştür: bilgisayar açılınca sistem
kendiliğinden kalkar, çökerse kendini yeniden başlatır. İlk aşamada fabrikada
sunucu yoktur (§2 özet); bu bölüm sunucuya geçilirse geçerlidir.

### Hazırlık (bir kez)

```bash
cd DALSAN-ISG                          # ya da OTOPARK-DEMO / LAFFOGATO
mkdir -p ayar && cp .env.example ayar/.env
                                       # ayar/.env: YONETICI_SIFRESI'ni doldurun
                                       # (Docker'da ZORUNLU), saklama süreleri vb.
bash models/indir.sh                   # yapay zeka modellerini indirir ve doğrular
```

> Docker'da ayarlar `ayar/.env` dosyasındadır (proje kökündeki `.env` değil):
> klasör olarak bağlanır ki ekrandaki **Ayarlar** sayfası da kaydedebilsin.
> Eski bir Docker kurulumundan geliyorsanız bir kez `mkdir -p ayar && mv .env ayar/.env`
> yapın. Şifre boşsa sistem açılmaz ve sebebini `docker compose logs` yazar.

> Model indirilmeden imaj derlenmez: derleme **"models/yolox_tiny.onnx
> bulunamadi"** diyerek durur. Bu bilinçlidir - modelsiz container hiçbir şey
> tespit etmeden sessizce çalışırdı. (Çift tıkla çalıştırmada model eksikse
> sistem ilk açılışta kendisi indirir; Docker'da imaj derlenmeden önce
> indirilmiş olmalıdır.)

### Başlatma

```bash
docker compose up -d        # arka planda başlat
docker compose logs -f      # günlüğü izle (Ctrl+C çıkar, sistem çalışmaya devam eder)
docker compose down         # durdur
```

Adres: `http://localhost:8080` (demolarda 8090 / 8100).

### Bilinmesi gerekenler

- **Veriler container dışında durur.** `veri/` ve `ayar/` klasörleri
  dışarıdan bağlanır; container silinse bile veritabanı, fotoğraflar ve
  ayarlar kaybolmaz.
- **Bilgisayarın kendi kamerası Docker'da görünmez** (Mac/Windows). Container
  içinde `KAYNAK=0` çalışmaz; RTSP adresi veya video dosyası kullanın.
- **GPU yalnızca Linux'ta ve bugünkü imajla çalışmaz.** İmaj yalnız CPU
  paketini (`onnxruntime`) kurar: `docker-compose.yml` içindeki `deploy:`
  bloğunu açıp `ayar/.env` dosyasında `CIKARIM_CIHAZI=cuda` yapmak tek başına
  yetmez; sistem CPU ile çalışır ve ana sayfada bunu yazar. GPU için
  `onnxruntime-gpu`'lu ayrı bir imaj gerekir (`docs/17-V2-TASARIM.md` §12.4).
  Mac/Windows'ta bu blok kapalı kalmalı.
- **Anons sesi Linux'ta:** sunucunun ses çıkışı (kablolu amfi ya da Bluetooth
  hoparlör) bir uyarı kanalıysa `docker-compose.ses.yml` de birlikte kullanılır;
  tarif o dosyanın başında ve `docs/14-ANONS-SISTEMI-BAGLAMA.md` §2.4'te (bu yol
  sunucuda henüz denenmedi). `/dev/snd` bağlamak artık kullanılmaz.

### Fabrika sunucusu kurulumu (özet)

```bash
git clone <depo-adresi> DALSAN-ISG && cd DALSAN-ISG
mkdir -p ayar && cp .env.example ayar/.env   # YONETICI_SIFRESI'ni doldurun
bash models/indir.sh
docker compose up -d
docker compose ps          # durum "healthy" görünmeli
```

> **Şifre Docker'da zorunludur.** Kapsayıcı ağ arayüzlerinin hepsini dinler;
> port satırı değiştirildiği anda şifresiz sistem ağa açılırdı. Bu yüzden
> `ayar/.env` içinde `YONETICI_SIFRESI` boşsa sistem açılmayı reddeder.

Sunucu yeniden başladığında sistem kendiliğinden kalkar (`restart:
unless-stopped`). Günlük yedek için `veri/` klasörünü zamanlanmış görevle
harici diske kopyalayın.

---

## 6. Ayarlar (.env dosyası)

Sık kullanılan satırlar:

| Ayar | Anlamı |
|---|---|
| `KAYNAK` | **Yalnızca demolarda** (otopark/bardak sayacı) kamera seçimi. DALSAN'da kameralar ekrandan eklenir, .env'de kaynak ayarı yoktur |
| `CIKARIM_CIHAZI` | `cpu` veya `cuda` (yalnız NVIDIA'lı Linux sunucuda `cuda`; o da `onnxruntime-gpu` ister, bugünkü kurulum ve imaj yalnız CPU paketini kurar) |
| `KARE_ORNEKLEME_FPS` / `KARE_FPS` | Saniyede kaç kare analiz edilsin (3-6 yeterli). DALSAN'da `KARE_ORNEKLEME_FPS` yalnız yeni eklenen kameranın varsayılanıdır; her kamerada ayrıca ayarlanır |
| `YONETICI_SIFRESI` | Boş = giriş sorulmaz (tek makine). Ağa açarken **doldurun** - en az 6 karakter |
| `ANONS` | DALSAN'da artık okunmaz: sesin hangi kanaldan çıkacağı (bu bilgisayarın ses çıkışı, Bluetooth hoparlör, IP hoparlör) **Anons sistemi** ekranındaki kanal listesinde tanımlanır. Eski `ANONS` satırı ilk açılışta bir kez "Tüm fabrika" kanalına aktarılır |
| `ANONS_HTTP_BICIMI` | IP hoparlörün beklediği biçim: `json`, `form`, `get` - hangi cihaz için hangisi: `docs/14-ANONS-SISTEMI-BAGLAMA.md` |
| `OLAY_SAKLAMA_GUN` vb. | Verinin ne kadar saklanacağı (KVKK politikasıyla uyumlu olmalı) |

Bölge, kural, mesafe eşiği gibi **sık değişen ayarlar .env'de değil ekrandadır**;
değiştirince sistem yeniden başlatılmaz, birkaç saniyede devreye girer.

---

## 7. Bir şey çalışmazsa

| Belirti | Sebep / çözüm |
|---|---|
| Çift tıklayınca hiçbir şey olmuyor (Mac) | İki ayrı sebep olabilir: **(1) Güvenlik uyarısı** → sağ tık → Aç → Aç. **(2) Çalıştırma izni yok** (ZIP'ten çıktıysa ya da Windows üzerinden kopyalandıysa) → Terminal'de proje klasöründe `chmod +x Baslat-Mac.command` |
| Mac'te "geliştirici araçları gerekiyor" penceresi | Python kurulu değil: python.org'dan Python 3.12 kurun |
| Mac'te "model indirilemedi, sertifika doğrulanamadı" | Uygulamalar → Python 3.x klasöründeki **Install Certificates.command** dosyasına çift tıklayın |
| "Python bulunamadı" (Windows) | Kurulumda "Add Python to PATH" işaretlenmemiş; Python'u kaldırıp kutuyu işaretleyerek tekrar kurun |
| Sayfa açılıyor ama görüntü yok | Kamera sayfasındaki durum satırı sebebi yazar: "dosya bulunamadı", "kameraya ulaşılamıyor (IP:port)", "kullanıcı adı/şifre yanlış olabilir"… |
| Kamera eklerken kırmızı hata sayfası | Sayfadaki mesaj ne yapılacağını söyler; "Geri dön ve düzelt" ile forma dönün (girdiğiniz bilgiler korunur) |
| "Kamera açılamadı" (Mac, Laffogato) | Kamera izni verilmemiş ya da kamerayı Zoom/FaceTime kullanıyor |
| Kutular çıkmıyor, sayaç 0 | Ana sayfada "Tespit modeli" satırına bakın: "İndiriliyor…" ise bekleyin, "Yüklenemedi" ise internet bağlantısını kontrol edip sistemi yeniden başlatın (ya da `bash models/indir.sh`) |
| Docker derlemesi "model bulunamadi" diyor | Derlemeden önce `bash models/indir.sh` çalıştırın |
| Docker'da kamera yok | Docker Desktop bilgisayar kamerasını veremez; RTSP veya video dosyası kullanın |
| Saatler 3 saat kaymış (Windows) | `pip install tzdata` (yeni kurulumlarda otomatik gelir) |

Günlükler: `veri/loglar/sistem.log` (fabrika sistemi) veya Docker'da
`docker compose logs -f`. Hata satırlarını (dosyada ve Docker'da
`"level": "ERROR"` geçenler, Kontrol Paneli'nde `[HATA]` ile başlayanlar)
**olduğu gibi kopyalayıp** sorarsanız çözmek kolay olur.

---

## 8. Yedekleme

```bash
# Tüm veriyi kopyalamak yeterlidir (veritabanı + fotoğraflar + ayarlar)
cp -R veri/ /Volumes/HariciDisk/dalsan-yedek-$(date +%Y-%m-%d)/
cp .env    /Volumes/HariciDisk/dalsan-yedek-$(date +%Y-%m-%d)/
```

Fabrika sisteminde ana sayfadaki **"Veritabanını Yedekle"** düğmesi, çalışırken
güvenli bir kopya alır (`veri/yedekler/` içine). Haftalık tam yedek için yine
`veri/` klasörünü kopyalayın.

**Test edilmemiş yedek, yedek değildir:** devreye almadan önce bir kez geri
yükleme provası yapın.

---

## 9. Bilerek kabul edilmiş sınırlar

- Nesne görüntüden çıkıp tekrar girerse yeni takip numarası alır ve yeniden
  sayılabilir.
- Kameraya uzak / çok küçük görünen nesneler için karar verilmez ("belirsiz").
- Kalibre edilmemiş kamerada mesafe kuralı **çalışmaz** - yaklaşık bir sayı
  uydurulmaz.
- Hazır tespit modeli genel amaçlıdır; forklift ve kafe bardağı gibi özel
  nesnelerde isabet, saha görüntüleriyle ince ayar yapılınca belirgin artar.
  Forklift için bu yol hazır: **Forklift** sayfası kareleri kameralardan toplar
  ve etiketletir, eğitim kapalı bir bilgisayarda tek komutla yapılır, çıkan
  model aynı sayfadan kurulur (`docs/06-OPERASYON.md` §9).
- Ham video **kaydedilmez**; yalnızca olay anı fotoğrafı saklanır (KVKK'da veri
  minimizasyonu). DALSAN'da KKD veri toplama açılırsa etiketlenecek kişi
  kırpıkları, forklift kare toplama açılırsa forklift eğitim kareleri de
  saklanır; iki toplama da varsayılanda kapalıdır.

Bunlar "sonra düzeltilecek eksikler" değil, yanlış alarmı azaltmak için
bilinçli olarak seçilmiş takaslardır.
