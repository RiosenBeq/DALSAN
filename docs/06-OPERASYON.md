# 06 — Operasyon

> Bu doküman **çalışan sistemi** anlatır. Mimari `docs/09-BASITLESTIRME-KARARLARI.md`
> ile sadeleştirildi: tek program, tek SQLite dosyası, tek container. Eski
> PostgreSQL + Alembic + üç servis kurgusu **artık yoktur**.

---

## 1. Kurulum

### 1.1 Günlük kullanım / geliştirme (Mac, Windows)

Docker gerekmez. Kontrol Paneli yeter:

| Mac | Windows |
|---|---|
| `Baslat-Mac.command` → çift tık | `Baslat-Windows.bat` → çift tık |

**İlk Kurulumu Yap** → **Sistemi Başlat**. Tarayıcı `http://127.0.0.1:8080`
adresinde açılır. Tespit modeli yoksa sistem ilk açılışta **kendisi indirir**
(internet gerekir); ana sayfadaki "Tespit modeli" satırı "Hazır" olana kadar bekleyin.

Ayrıntı: `NASIL-CALISIR.md`.

### 1.2 Fabrika sunucusu (Linux + Docker)

```bash
git clone <depo-adresi> && cd DALSAN
mkdir -p ayar && cp .env.example ayar/.env
                           # ayar/.env: YONETICI_SIFRESI (ZORUNLU), saklama süreleri,
                           # ANONS, tespit eşikleri — anons tarifi: docs/14
bash models/indir.sh       # model ağırlıkları repoda yoktur; indirilen dosya doğrulanır
docker compose up -d
docker compose ps          # tek servis: dalsan — durum "healthy" olmalı
```

Erişim: `http://127.0.0.1:8080` (compose varsayılanı sunucunun kendisine açar).

> **Docker'da ayarlar `ayar/.env` dosyasındadır** ve klasör olarak bağlanır
> (tek dosya bağlandığında ekrandaki Ayarlar sayfası kaydedemiyordu). Eski bir
> Docker kurulumundan geliyorsanız bir kez: `mkdir -p ayar && mv .env ayar/.env`.
> Dosya yoksa sistem açılmaz ve `docker compose logs` bu tarifi yazar.
>
> **Şifre Docker'da zorunludur.** `YONETICI_SIFRESI` boşsa sistem açılmayı
> reddeder: kapsayıcı ağ arayüzlerinin hepsini dinler ve `docker-compose.yml`
> içindeki port satırı `"8080:8080"` yapıldığı anda şifresiz sistem ağa açılır,
> ağdaki herkes kamera silebilir, kural değiştirebilir ve hoparlörden anons
> yaptırabilirdi. Şifre en az 6 karakter olmalıdır. Port satırını açarken
> tarayıcıya yazılacak adresi `IZINLI_SUNUCU_ADLARI` satırına ekleyin (docs/15).
> Ekrandan da ayarlanabilir: **Komuta → Ayarlar → Güvenlik**.

Şema **otomatik** uygulanır: açılışta `backend/sema/*.sql` sırayla çalışır ve
uygulananlar `sema_surumu` tablosuna yazılır. Ayrı migrasyon komutu yoktur.

### 1.2.1 Sunucu yeniden başlayınca sistem kendiliğinden kalkmalı (K8)

Docker kurulumunda bu **hazırdır**: `docker-compose.yml` içindeki
`restart: unless-stopped` satırı, sunucu yeniden başladığında container'ı da
başlatır. Tek koşul, Docker servisinin kendisinin açılışta başlamasıdır:

```bash
sudo systemctl enable docker
```

**Provası (atlanmayacak):** sunucuyu gerçekten yeniden başlatın ve sistem
kendiliğinden açılmış mı bakın.

```bash
sudo reboot
# sunucu açıldıktan ~1 dk sonra:
docker compose ps            # durum "healthy" olmalı
curl -fs "http://127.0.0.1:8080/saglik?hazirlik=1"   # "hazir": true
```

**Docker kullanılmıyorsa** (sistem doğrudan Python ile çalışıyorsa) aynı işi
systemd yapar. `/etc/systemd/system/dalsan.service` dosyasını oluşturun —
`<KURULUM-YOLU>` ve `<KULLANICI>` kendi değerlerinizle değişir:

```ini
[Unit]
Description=DALSAN ISG Goruntu Analiz Sistemi
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=<KULLANICI>
WorkingDirectory=<KURULUM-YOLU>
ExecStart=<KURULUM-YOLU>/.venv/bin/python -m uvicorn app.main:app \
          --host 127.0.0.1 --port 8080 --app-dir backend \
          --timeout-graceful-shutdown 3
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now dalsan
sudo systemctl status dalsan      # "active (running)" olmalı
```

`Restart=always`, sistem bir hata yüzünden kapanırsa da 10 saniye içinde
yeniden başlatır — 7x24 çalışmanın gereği.

**Takılan analiz de yeniden başlasın.** Analiz takılırsa (görüntü geliyor ama
90 sn'dir hiçbir kare işlenmiyor) bekçi "Analiz takıldı" olayı yazar ve komuta
ekranlarında kırmızı şerit çıkar. Takılan bir iş parçacığı program içinden
kurtarılamaz; sunucu kurulumunda (Docker ya da systemd) `.env`'e

```
BEKCI_TEPKISI=yeniden_baslat
```

yazın: program olayı yazıp kendini kapatır, `restart: unless-stopped` ya da
`Restart=always` yeniden açar. Masaüstü programında bu ayar etkisizdir — orada
program Kontrol Paneli'yle aynı süreçte çalışır ve yalnız uyarır.

### 1.2.2 Yedekten geri yükleme provası (K7)

**Prova edilmemiş bir yedek, yedek değildir.** Kurulum tamamlandıktan sonra
bunu bir kez yapın:

1. İzleme ekranındaki **"Yedek Al"** düğmesine basın → `veri/yedekler/` altına
   bir `.db` dosyası düşer.
2. Sisteme bir deneme kamerası ekleyin (sonra silinecek).
3. Kontrol Paneli'nde **Durdur**'a basın. *(Geri yükleme sistem çalışırken
   yapılamaz: veritabanı dosyası açıktır ve altından değiştirmek veri kaybıdır.
   Düğme zaten reddeder.)*
4. **"Yedekten Geri Yükle"** → 1. adımdaki dosyayı seçin → onaylayın.
5. **Sistemi Başlat** → deneme kamerasının **kaybolmuş** olması gerekir.

Geri yükleme, mevcut veritabanının bir kopyasını `veri/yedekler/` altına
`geri-yukleme-oncesi-...db` adıyla alır; yanlış yedeği seçtiyseniz aynı
düğmeyle ona dönebilirsiniz.

Docker kurulumunda Kontrol Paneli yoktur; orada geri yükleme elle yapılır:

```bash
docker compose stop
cp veri/dalsan.db veri/yedekler/geri-yukleme-oncesi-$(date +%F_%H-%M).db
cp veri/yedekler/<SECILEN-YEDEK>.db veri/dalsan.db
rm -f veri/dalsan.db-wal veri/dalsan.db-shm   # bayat WAL yeni dosyayı bozar
docker compose start
```

> `-wal` ve `-shm` dosyalarını silmek **şart**: SQLite bunları bulursa eski
> günlüğü yeni veritabanının üstüne uygular.

### 1.3 Verinin ve ayarların yeri

İki soru birbirinden ayrıdır ve ikisi de `backend/app/kaynaklar.py` içinde,
**tek yerde** çözülür:

| | Depodan çalışırken (bugün) | Paketlenmiş programda |
|---|---|---|
| Kaynak dosyalar (şablon, stil, şema betiği) | depo kökü | programın açtığı geçici klasör (`sys._MEIPASS`) |
| Yazılabilir veri (`veri/`, `models/`, `.env`) | depo kökü | macOS: `~/Library/Application Support/NextGen Detector/` · Windows: `%LOCALAPPDATA%\NextGen Detector\` |

Neden ayrı: paketlenmiş uygulamanın kendisi **salt okunurdur**; veritabanı,
günlük ve indirilen model oraya yazılamaz.

**Veri asla kendiliğinden taşınmaz.** Paketlenmiş program, kendi yanındaki
klasörde bir `veri/dalsan.db` bulur ve yeni konum boşsa **eski konumu
kullanmaya devam eder**; durumu günlüğe yazar. Sessiz kopyalama yapılsaydı,
yarıda kalan bir taşımada ya da yedeğini eski klasörde arayan kullanıcıda
kayıtlar kaybolmuş sayılırdı.

Paketlenmiş programda `.env` dosyası ilk açılışta `.env.example`'dan **bir kez**
üretilir; sonraki açılışlarda üzerine yazılmaz.

`veri/oturum.anahtar` giriş çerezlerini imzalayan, kuruluma özgü rastgele
sırdır. İlk girişte üretilir ve yalnız sahibi okuyabilir. Kimseyle paylaşmayın.
Silinirse yenisi üretilir ve açık oturumlar bir kez düşer; başka zararı yoktur.

---

## 2. Servis

Tek servis: `dalsan` (FastAPI + arka planda analiz iş parçacığı).

| Özellik | Değer |
|---|---|
| Restart | `unless-stopped` — sunucu yeniden başlarsa sistem kendiliğinden kalkar (K8) |
| Healthcheck | `GET /saglik?hazirlik=1` (30 sn arayla); sistem hazır değilse 503 → "unhealthy" |
| Veri | `./veri` container dışında bağlı — container silinse de kaybolmaz |
| Ayarlar | `./ayar/.env`, dizinle ve yazılabilir bağlanır (Ayarlar sayfası kaydedebilsin diye, R27) |

`/saglik` ucu bilerek ucuzdur: ana sayfa `veri/` klasörünün tamamını tarayıp
boyut hesapladığı için sağlık kontrolünde kullanılmaz. Her durumda 200 ve
`"durum": "calisiyor"` döner (Kontrol Paneli portun bu sisteme ait olduğunu
buna bakarak anlar); yalnız `?hazirlik=1` hazır olmayan sistemde 503 döner.
Docker "unhealthy" container'ı **yeniden başlatmaz** — bu yalnız görünürlüktür;
takılan analizi bekçi yeniden başlatır (§1.2.1).

Şifresiz gövde yalnız `durum`, `analiz`, `model`, `hazir` ve `sorunlar`
kodlarını verir. Kamera başına okunan/işlenen hız, işleme süresi (p50/p90), son
karenin yaşı, boş disk ve analiz turunun yaşı `?ayrinti=1` ile ve oturum açıkken
gelir (şifre tanımlı değilse oturum gerekmez).

| `sorunlar` kodu | Anlamı | `hazir`'ı bozar |
|---|---|---|
| `analiz_takildi` | Görüntü geliyor ama analiz ilerlemiyor (bekçi) | evet |
| `analiz_olu` | Analiz iş parçacığı çalışmıyor | evet |
| `model_yuklenemedi` | Tespit modeli yüklenemedi | evet |
| `veritabani_acilamadi` | Sağlık denetimi veritabanını okuyamadı | evet |
| `olay_yazilamadi` | Son ihlal kayda geçmedi (anons yine çaldı) | evet |
| `kritik_kural_pasif` | Mesafe ya da hız kuralı kalibrasyon bekliyor, çalışmıyor | hayır (ekranda kırmızı) |
| `ort_paket_cakismasi` | İki ONNX Runtime paketi birlikte kurulu; GPU sessizce kaybolabilir | hayır |

---

## 3. Güncelleme

```bash
git pull
docker compose build
docker compose up -d
docker compose logs -f --tail=100
```

Şema değişikliği varsa açılışta kendiliğinden uygulanır.

> **23.09.2026 sürümüne geçerken bir kez:** ayar dosyası artık `ayar/.env`
> olarak bağlanıyor ve Docker'da şifre zorunlu. `docker compose up -d`'den önce
> `mkdir -p ayar && mv .env ayar/.env` yapın ve `YONETICI_SIFRESI`'nin dolu
> olduğunu kontrol edin; yoksa sistem açılmaz ve sebebini günlüğe yazar.
>
> Aynı sürümde oturum çerezleri kuruluma özgü bir sırla imzalanmaya başladı
> (R16): güncellemeden sonra herkes **bir kez** yeniden giriş yapar.

Geri alma:
`git checkout <önceki-sürüm>` → `docker compose build` → `up -d`.

> Şema betikleri **geri alınamaz** (Alembic yoktur — `docs/09` kararı). Geri
> dönüş yolu yedektir: sürüm yükseltmeden ÖNCE `veri/` klasörünü kopyalayın.

---

## 4. Yedekleme

**Tam yedek = `veri/` klasörünü ve ayar dosyasını kopyalamak.** Hepsi bu.
Ayar dosyası Docker kurulumunda `ayar/.env`, Kontrol Paneli kurulumunda
proje kökündeki `.env`'dir.

```bash
cp -R veri/    /yedek/dalsan-$(date +%Y-%m-%d)/
cp ayar/.env   /yedek/dalsan-$(date +%Y-%m-%d)/     # Docker; panelde: cp .env
```

Sistem çalışırken güvenli veritabanı kopyası için: ana sayfadaki
**"Veritabanını Yedekle"** düğmesi (`veri/yedekler/` içine SQLite backup API ile
yazar, WAL uyumludur). Fotoğrafları kapsamaz — haftalık tam yedeği ihmal etmeyin.

**Geri yükleme provası — devreye almadan önce zorunlu (K7):**

```bash
docker compose down
mv veri veri-eski && cp -R /yedek/dalsan-YYYY-AA-GG/veri veri
docker compose up -d          # olaylar ve fotoğraflar yerinde mi, ekrandan bakın
```

Test edilmemiş yedek yedek sayılmaz. 7. haftada bir kez tam prova yapılır ve
sonucu kabul tutanağına yazılır.

---

## 5. Retention (saklama süreleri)

Bakım, analiz süreci içinde **uygulama açıldıktan hemen sonra bir kez** ve sonra
her 24 saatlik çalışma süresinde bir çalışır. Ayrı zamanlanmış görev yoktur.

| Veri | Ayar | Varsayılan | Not |
|---|---|---|---|
| İhlal olayları (DB) | `OLAY_SAKLAMA_GUN` | 180 gün | KVKK politikasıyla uyumlu olmalı |
| Kanıt fotoğrafları | `GORUNTU_SAKLAMA_GUN` | 90 gün | Disk büyümesinin ana kalemi |
| Etiketlenmemiş KKD kırpıkları | `KKD_HAM_VERI_SAKLAMA_GUN` | 30 gün | **Etiketlenenler silinmez** — eğitim veri setidir |
| Sistem olayları | `SISTEM_OLAY_SAKLAMA_GUN` | 90 gün | |

Bu dört süre, disk uyarı sınırı, anons adresi ve tespit eşikleri **arayüzden**
de değiştirilebilir: soldaki raftan **Sistem ayarları** (`/ayarlar`). Sayfa
`.env` dosyasını açıklama satırlarını bozmadan günceller ve değeri yazmadan
önce açılıştaki doğrulayıcıdan geçirir — geçersiz bir ayar dosyaya yazılmaz.
**Değişiklik, sistem yeniden başlatılınca geçerli olur.**

Fotoğrafı silinen olayın kaydı korunur, yalnızca fotoğraf bağlantısı temizlenir
(olay ekranında kırık resim çıkmaz).

Boş disk `DISK_UYARI_GB` altına inince Olaylar listesine `Sistem` tipi bir uyarı
düşer. **DALSAN'ın KVKK saklama politikasıyla uyum 1. haftada teyit edilir** —
sistem politikayı teknik olarak zorlar, politikayı belirlemez.

---

## 6. Log okuma

Günlük dosyası: `veri/loglar/sistem.log` (5 MB'ta döner, son 3 kopya saklanır).
Kontrol Paneli aynı satırları penceresinde gösterir.

```bash
tail -f veri/loglar/sistem.log
grep '"level": "ERROR"' veri/loglar/sistem.log
grep '"bilesen": "kamera"' veri/loglar/sistem.log
docker compose logs -f            # Docker kurulumunda
```

Biçim: her satır tek bir JSON nesnesi — `ts, level, bilesen, mesaj`.
Sorun bildirirken kırmızı/`ERROR` satırlarını **olduğu gibi** kopyalayın.

Web sunucusunun (uvicorn) satırları da aynı biçimde ve aynı dosyadadır:
`"bilesen": "uvicorn.error"` sunucunun açılışı, kapanışı ve beklenmeyen
hataları; `"bilesen": "uvicorn.access"` HTTP istekleri. Erişim satırlarından
yalnız **değiştiren** istekler (kural, kamera, bölge kaydı: POST/PUT/DELETE) ve
hata yanıtları (4xx/5xx) yazılır. Başarılı sayfa ve yoklama istekleri yazılmaz:
Kontrol Paneli 1,5 sn'de bir sağlık ucunu yoklar, hepsi yazılsaydı dönen günlük
önemli satırları iki günde dışarı iterdi.

```bash
grep '"bilesen": "uvicorn' veri/loglar/sistem.log
```

**Beklenen tek `ERROR` satırı:** sistem durdurulurken bir tarayıcıda Olaylar ya
da komuta ekranı açıksa uvicorn `Cancel 1 running task(s), timeout graceful
shutdown exceeded` yazar. Ekranın canlı akışı kendiliğinden bitmez; kapanış
onu 3 sn bekleyip keser (başlatma komutlarındaki `--timeout-graceful-shutdown 3`),
sayfa da kendiliğinden yeniden bağlanır. Bu süre olmasaydı kapanış hiç bitmez,
Kontrol Paneli süreci zorla kapatırdı. Hemen ardından Olaylar'da "Sistem durdu"
görünmelidir.

---

## 7. Sorun giderme

| Belirti | Bakılacak yer |
|---|---|
| Kamera "bağlanıyor"da kalıyor | Kamera sayfasındaki durum satırı sebebi yazar (ulaşılamıyor / şifre / dosya yok). İlk bağlantı 30 sn sürebilir |
| Kamera "çevrimdışı" | Aynı durum satırı + `veri/loglar/sistem.log` içinde `"bilesen": "kamera"`; NVR eşzamanlı bağlantı limiti sık sebeptir |
| "Tespit modeli: Yüklenemedi" | İnternet yoksa `bash models/indir.sh` ile elle indirin; dosya bozuksa silip tekrar indirin |
| Kutular çıkmıyor / nesne kaçıyor | `.env` içinde `TESPIT_GUVEN_ESIGI` ve `TESPIT_INSAN_GUVEN_ESIGI` değerlerini kademeli düşürün (0,05'lik adımlarla). Uzak nesnede `TESPIT_EN_KUCUK_KENAR_PX` düşürülür |
| Çok fazla yanlış tespit | Aynı eşikleri yükseltin; **NextGen AI İsabetli** (`MODEL_DOSYASI=models/yolox_s.onnx`) daha isabetlidir (daha yavaş) |
| Olay üretilmiyor | Kural açık mı; bölge doğru tipte mi; mesafe kuralında kalibrasyon var mı (Kurallar sayfasındaki rozet söyler) |
| KKD sayfasına yeni örnek düşmüyor | Sayfanın üstündeki "Veri toplama" kapısı **KAPALI** olabilir (varsayılan). Rev.02 onayından sonra açılır; kapalıyken kişi görüntüsü bilerek toplanmaz. Açıksa: kişi KKD zorunlu alanda mı, muaf alanın dışında mı, kural boyundan (`min_person_height_px`) uzun mu |
| KKD hiç olay üretmiyor | Model henüz eğitilmedi — bu **beklenen** davranıştır (docs/04). KKD sekmesinin üstündeki "KKD modeli" kartı durumu yazar; veri toplanıyor mu da orada |
| KKD sekmesinde "KKD modeli yüklenmedi" | Model dosyası `models/SHA256SUMS`'taki özetle tutmuyor ya da özet satırı yok, açılamıyor veya sözleşmeye uymuyor (docs/04 §6.6). Kartta sebep yazar; modeli veren uzmandan doğru dosyayı ve özet satırını isteyin, sonra yeniden başlatın. Bu sırada diğer kurallar çalışır |
| KKD çok fazla yanlış alarm | `04-KKD-BARET-YELEK.md` §8.3 tablosu; kabindeki sürücü için kuralın "sürücüyü değerlendirme" kutusu, üst üste kişi ve bulanıklık için kural formundaki iki eşik (docs/03 §3) |
| Olaylar'da "KKD modeli değişti … gölge moda alındı" | Yüklü KKD modeli, anonsu açılırken onaylanan sürüm değil (ya da hiç onaylanmamış). Beklenen güvenlik davranışı: olaylar kaydedilir, hoparlör susar. Yeni sürüm gölgede incelenip ölçüldükten sonra anons Komuta → Uyarı zinciri'nden yeniden açılır |
| Rapor'da yanlış alarm / saat "ölçülemedi" ya da kapsama düşük | O kameranın bazı günlerinde işaretlenmemiş ihlal var. Komuta → İnceleme'de o günlerin olaylarını "İncelendi" ya da "Yanlış alarm" diye işaretleyin: oran yalnız bütün ihlalleri işaretli günlerden hesaplanır. "Analiz edilen: —" ise o dönemde analiz kaydı yok (model yüklenmemiş, kamera kopuk ya da dönem bu kayıt başlamadan önce) |
| Uyarılar gecikiyor | Kamera `sample_fps` değerini düşürün; substream kullanın; `CIKARIM_CIHAZI=cuda` (yalnız NVIDIA'lı Linux) |
| "cuda seçili ama CPU ile çalışıyor" | Ana sayfada uyarı olarak görünür: NVIDIA sürücüsü + `onnxruntime-gpu` gerekir, ya da `.env`'de `cpu` yapın |
| Anons çalmıyor | **Anons** sayfası → "Anonsu Dene". Sonuç satırı sebebi yazar (ses dosyası yok / adres yanlış / komut bulunamadı) |
| Ekranda uyarı sesi gelmiyor | Sağ alttaki ses çipi sebebini yazar: "KAPALI" ise tıklayın (ses bu tarayıcıda açılır); "beklemede" ise sayfaya bir kez tıklayın (tarayıcı kuralı: ses ancak bir tıklamadan sonra çalar); "çalışmıyor" ise tarayıcı ses çalamıyor — başka bir tarayıcı deneyin. Çip yoksa ekran sesi çalışıyordur |
| Komuta ekranının üstünde kırmızı şerit | Uyarı üretilmiyor ya da kaydedilmiyor (analiz takıldı, model yüklenemedi…), kritik bir kural çalışmıyor ya da bir kameradan görüntü gelmiyor; şerit hangisi olduğunu yazar, "Ayrıntı →" Sağlık ekranını açar. Gri şerit: durum doğrulanamıyor (sunucuya ulaşılamıyor ya da model yükleniyor) |
| Disk doluyor | Ana sayfadaki "Boş alan"; saklama sürelerini kısaltın; `veri/goruntuler` en büyük kalemdir |
| Herkes aynı anda oturumdan düştü | Şifre değişti, sistem yeni sürüme güncellendi ya da `veri/oturum.anahtar` silindi veya bozuldu (yenisi üretilir, günlükte uyarı). Yeniden giriş yapmak yeter |
| Kamera ya da hoparlör formunda adres `••••@` ile görünüyor | Beklenen: kullanıcı adı ve şifre sayfaya basılmaz. •••• olduğu gibi bırakılırsa kayıtlı şifre korunur, ip ya da yol değişse de. Değiştirmek için •••• yerine `kullanici:sifre` yazın |
| Canlı uyarı paneli "bağlantı koptu" | Sunucu durmuş olabilir; Kontrol Paneli'nden yeniden başlatın |
| Olaylar'da "Analiz takıldı" ya da "Analiz durdu" | Görüntü geliyor ama analiz ilerlemiyor: o sürede **hiçbir uyarı üretilmiyor**. Sistemi yeniden başlatın (sunucuda `BEKCI_TEPKISI=yeniden_baslat` bunu kendiliğinden yapar, §1.2.1). `veri/loglar/sistem.log` içinde `"bilesen": "bekci"` satırından önceki hatalara bakın |
| Olaylar'da "Analiz yavaşladı" | Ya kamerada kare üst üste işlenemedi (hattı yeniden kuruldu; günlükte "Kare işlenemedi" satırları sebebi yazar) ya da işlenen görüntü hızı hedefin altında kaldı: kamera `sample_fps`'ini düşürün, kamera sayısını azaltın ya da daha güçlü donanım kullanın. Eşikler Ayarlar → Analiz sağlığı |
| Olaylar'da "Sistem başladı — önceki çalışma düzgün kapanmamıştı" | Sistem "Sistem durdu" yazamadan kapandı: elektrik kesintisi, bilgisayarın kapatılması, görev yöneticisinden sonlandırma ya da çökme. O sırada açık kalan olaylar "sistem yeniden başladı" sebebiyle kapatılmıştır. Sık görülüyorsa `veri/loglar/sistem.log`'un kapanıştan önceki son satırlarına bakın |

---

## 8. Devreye alma kontrol listesi (8. hafta)

- [ ] Sistem, sunucu yeniden başlatma sonrası kendiliğinden ayakta (K8)
- [ ] 3-4 kameranın tamamı ≥ 24 saat kesintisiz `çevrimiçi` (K1)
- [ ] Bölge ve kurallar arayüzden değiştirilebiliyor, restart gerekmiyor (K3)
- [ ] Test ihlali ≤ 2 sn içinde ekrana düşüyor (K4)
- [ ] Olay kaydı + kanıt fotoğrafı doğru, filtre çalışıyor (K5)
- [ ] Anons: **Anons sayfasından denendi**, çalışıyor veya "altyapı uygun değil" olarak yazılı kayıt altında (K6)
- [ ] Yedek alındı, **geri yükleme prova edildi** (K7)
- [ ] KKD gölge modda ≥ 3 gün çalıştı, precision ölçüldü, eşikler ayarlandı (K10, K11)
- [ ] KKD anonsu ancak precision kabul edildikten **sonra** açıldı
- [ ] Yanlış alarm hedefi ölçüldü: Komuta → Rapor'da her kamera için incelemesi tam günlerden hesaplanan yanlış alarm / saat, hedefin (saatte en çok 2) altında (`17-V2-TASARIM.md` §14)
- [ ] Bakım (retention) çalıştığı günlükten doğrulandı, KVKK süreleriyle uyumlu
- [ ] **Giriş şifresi geri eklendi** (`docs/07` #0) — ağa açık kurulumda zorunlu
- [ ] Kullanım dokümanı teslim edildi, kullanıcı eğitimi yapıldı (K9)
- [ ] Kabul tutanağı: K1-K11 madde madde işaretlendi
