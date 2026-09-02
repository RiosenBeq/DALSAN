# Nasıl Çalışır — Kurulum ve Çalıştırma Kılavuzu

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
        │  saniyede 3-6 kare örneklenir (hepsi değil — işlemci boğulmasın)
        ▼
   TESPİT       Görüntüde ne var? (insan, araç, bardak…)  → YOLOX modeli
        ▼
   TAKİP        Aynı nesne mi, yeni nesne mi? → her nesneye bir takip numarası
        ▼
   KARAR        Kural motoru: bölgede mi, kaç saniyedir, kaç metre uzakta,
                bardak hangi tarafta… (kare değil, TAKİP bazlı karar)
        ▼
   KAYIT        Olay + kanıt fotoğrafı → tek dosyalık veritabanı
        ▼
   EKRAN        Tarayıcıdaki sayfa; 1-2 saniyede bir kendini günceller
```

**Neden "takip bazlı karar":** tek bir karede yanılmak kolaydır (gölge, toz,
hareket bulanıklığı). Sistem bir nesneyi birkaç saniye izler, sonra karar
verir. Bu yüzden sayılar birkaç saniye gecikmeyle görünür — bu bir yavaşlık
değil, yanlış alarmı önleyen bilinçli bir tasarımdır.

**Karar verilemeyen durumlar "belirsiz" yazılır**, ihlal sayılmaz. Kanıtın
yokluğu, ihlalin varlığı değildir.

**Tek program:** Web sayfası ve analiz aynı program içinde çalışır. Başlatılacak
tek şey, bakılacak tek günlük vardır.

**Tek veri klasörü:** `veri/` — veritabanı, olay fotoğrafları, günlükler.
**Yedekleme = bu klasörü kopyalamak.**

---

## 2. Ne nerede çalışır (dürüst tablo)

| | Mac (çift tık) | Windows (çift tık) | Docker (Mac/Win) | Docker (Linux sunucu) |
|---|---|---|---|---|
| Sistemin kendisi, arayüz | ✅ | ✅ | ✅ | ✅ |
| Video dosyasıyla deneme | ✅ | ✅ | ✅ | ✅ |
| **IP kamera (RTSP)** | ✅ | ✅ | ✅ | ✅ |
| **Bilgisayarın kendi kamerası** | ❌ *(DALSAN yalnız RTSP ve video dosyası kabul eder)* | ❌ | ❌ | ❌ |
| **Ekran kartı (GPU) hızlandırma** | ❌ *(Mac'te Docker GPU yok)* | ⚠️ WSL2 + NVIDIA ile | ❌ | ✅ NVIDIA + Container Toolkit |
| Anons — ses kartı | ✅ | ✅ | ❌ | ✅ *(`/dev/snd` bağlanırsa)* |
| Anons — IP hoparlör (HTTP) | ✅ | ✅ | ✅ | ✅ |
| 7/24 kendiliğinden çalışma | ⚠️ pencere açık kalmalı | ⚠️ pencere açık kalmalı | ✅ | ✅ |

**Özet karar:**
- **Geliştirme ve deneme** → Mac/Windows'ta çift tık. Docker gereksiz.
- **Kafe demoları (Laffogato'nun canlı kamerası)** → çift tık; Docker'da
  bilgisayar kamerası çalışmaz.
- **Fabrika kurulumu (7/24, GPU)** → Linux sunucu + Docker.

---

## 3. Mac'te çalıştırma

1. [python.org](https://www.python.org/downloads/) → **Python 3.12** kur.
2. Proje klasöründeki **Baslat-Mac.command** dosyasına **çift tıkla**.
   İlk açılışta gerekli paketleri kendisi kurar (birkaç dakika sürer).
3. Tarayıcı kendiliğinden açılır.

İlk açılışta macOS "geliştirici doğrulanamadı" derse: **sağ tık → Aç → Aç**.

**Kamera izni (Laffogato):** bilgisayarın kamerasını ilk kullanışta macOS izin
sorar → **İzin Ver**. Sonradan değiştirmek için: Sistem Ayarları → Gizlilik ve
Güvenlik → Kamera.

**Pencereyi kapatmak sistemi durdurur.** Fabrika kurulumu bunun için değil,
Docker içindir (aşağıya bakın).

---

## 4. Windows'ta çalıştırma

1. [python.org](https://www.python.org/downloads/) → **Python 3.12** kur.
   Kurulum ekranında **"Add Python to PATH"** kutusunu işaretle — en kritik adım.
2. **Baslat-Windows.bat** dosyasına **çift tıkla**.
   SmartScreen uyarısı çıkarsa: Daha fazla bilgi → Yine de çalıştır.
3. Tarayıcı kendiliğinden açılır.

Windows'a özel olarak halledilmiş şeyler:
- **Başlatıcı:** `py -3` ile başlatılır. `where python` Windows 10/11'de Python
  kurulu olmasa bile başarılı olur (Microsoft Store takma adı yüzünden) ve
  Mağaza'yı açıp pencereyi kapatırdı.
- **Türkçe günlük:** Kontrol Paneli alt sürecin çıktısını UTF-8 okur. Aksi halde
  büyük Ş/Ğ harfleri Windows'un cp1254 kod sayfasında çözülemiyor ve günlük
  penceresi sessizce donuyordu.
- **Saat dilimi:** Windows saat dilimi veritabanıyla gelmez; `tzdata` paketi
  bağımlılıklara eklendi, saatler Türkiye saatinde doğru gösterilir.
- **Anons sesi:** `afplay`/`aplay` Windows'ta yoktur; PowerShell'in hazır ses
  çalıcısı kullanılır. **Yalnızca .wav çalar** — sistem başka biçimi kabul etmez.
- **Türkçe klasör adı:** Kanıt ve KKD fotoğrafları `C:\Users\Gökhan\...` gibi
  yollara da yazılabilir (OpenCV'nin yol kodlaması atlanır).
- **Kamera:** Kaynak olarak yalnızca RTSP adresi veya video dosyası kullanılır;
  bilgisayarın kendi kamerası DALSAN kapsamında değildir.

---

## 5. Docker ile çalıştırma

Docker, **fabrika sunucusu için** düşünülmüştür: bilgisayar açılınca sistem
kendiliğinden kalkar, çökerse kendini yeniden başlatır.

### Hazırlık (bir kez)

```bash
cd DALSAN-ISG          # ya da OTOPARK-DEMO / LAFFOGATO
cp .env.example .env   # ayarları düzenleyin (kamera adresi, saklama süreleri)
bash models/indir.sh   # yapay zeka modelini indirir
```

> Model indirilmeden imaj derlenmez: derleme **"models/yolox_tiny.onnx
> bulunamadi"** diyerek durur. Bu bilinçlidir — modelsiz container hiçbir şey
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

- **Veriler container dışında durur.** `veri/` klasörü ve `.env` dosyası
  dışarıdan bağlanır; container silinse bile veritabanı, fotoğraflar ve
  ayarlar kaybolmaz.
- **Bilgisayarın kendi kamerası Docker'da görünmez** (Mac/Windows). Container
  içinde `KAYNAK=0` çalışmaz; RTSP adresi veya video dosyası kullanın.
- **GPU yalnızca Linux'ta.** `docker-compose.yml` içindeki `deploy:` bloğunu
  açın ve `.env` dosyasında `CIKARIM_CIHAZI=cuda` yapın. Mac/Windows'ta bu
  blok kapalı kalmalı.
- **Anons sesi Linux'ta:** compose dosyasındaki `devices: /dev/snd` satırını açın.

### Fabrika sunucusu kurulumu (özet)

```bash
git clone <depo-adresi> && cd DALSAN-ISG
cp .env.example .env
bash models/indir.sh
docker compose up -d
docker compose ps          # durum "healthy" görünmeli
```

> **Dikkat:** Giriş şifresi şu an bilerek kapalıdır (geliştirme aşaması).
> Fabrika sunucusunda sistem ağdaki her bilgisayardan açılabilir; sunucuya
> kurmadan ÖNCE şifre geri eklenmelidir (`docs/07-YOL-HARITASI.md` #0).

Sunucu yeniden başladığında sistem kendiliğinden kalkar (`restart:
unless-stopped`). Günlük yedek için `veri/` klasörünü zamanlanmış görevle
harici diske kopyalayın.

---

## 6. Ayarlar (.env dosyası)

Sık kullanılan satırlar:

| Ayar | Anlamı |
|---|---|
| `KAYNAK` | **Yalnızca demolarda** (otopark/bardak sayacı) kamera seçimi. DALSAN'da kameralar ekrandan eklenir, .env'de kaynak ayarı yoktur |
| `CIKARIM_CIHAZI` | `cpu` veya `cuda` (yalnız NVIDIA'lı Linux sunucuda `cuda`) |
| `KARE_ORNEKLEME_FPS` / `KARE_FPS` | Saniyede kaç kare analiz edilsin (3-6 yeterli) |
| `ANONS` | `null` (kapalı), `ses_karti`, `http` |
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
`docker compose logs -f`. Kırmızı/`ERROR` satırlarını **olduğu gibi kopyalayıp**
sorarsanız çözmek kolay olur.

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
- Kalibre edilmemiş kamerada mesafe kuralı **çalışmaz** — yaklaşık bir sayı
  uydurulmaz.
- Hazır tespit modeli genel amaçlıdır; forklift ve kafe bardağı gibi özel
  nesnelerde isabet, saha görüntüleriyle ince ayar yapılınca belirgin artar.
- Ham video **kaydedilmez**; yalnızca olay anı fotoğrafı saklanır (KVKK'da veri
  minimizasyonu).

Bunlar "sonra düzeltilecek eksikler" değil, yanlış alarmı azaltmak için
bilinçli olarak seçilmiş takaslardır.
