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
cp .env.example .env       # saklama süreleri, ANONS, tespit eşikleri
                           # anons bağlama tarifi: docs/14-ANONS-SISTEMI-BAGLAMA.md
bash models/indir.sh       # model ağırlıkları repoda yoktur
docker compose up -d
docker compose ps          # tek servis: dalsan — durum "healthy" olmalı
```

Erişim: `http://127.0.0.1:8080` (compose varsayılanı sunucunun kendisine açar).

> **Ağa açmadan önce şifre koyun.** `.env` dosyasındaki `YONETICI_SIFRESI`
> satırı boşken giriş sorulmaz — bu, yalnızca `127.0.0.1`'den açılan tek
> makinelik kurulum içindir. `docker-compose.yml` içindeki port satırını
> `"8080:8080"` yapmadan ÖNCE şifreyi doldurun; aksi halde ağdaki herkes
> kamera silebilir, kural değiştirebilir ve hoparlörden anons yaptırabilir.
> Şifre en az 6 karakter olmalıdır; sistem daha kısasını açılışta reddeder.
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
curl -fs http://127.0.0.1:8080/saglik
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
ExecStart=<KURULUM-YOLU>/.venv/bin/python -m uvicorn app.main:uygulama \
          --host 127.0.0.1 --port 8080 --app-dir backend
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

---

## 2. Servis

Tek servis: `dalsan` (FastAPI + arka planda analiz iş parçacığı).

| Özellik | Değer |
|---|---|
| Restart | `unless-stopped` — sunucu yeniden başlarsa sistem kendiliğinden kalkar (K8) |
| Healthcheck | `GET /saglik` (30 sn arayla) |
| Veri | `./veri` container dışında bağlı — container silinse de kaybolmaz |
| Ayarlar | `./.env` salt okunur bağlanır |

`/saglik` ucu bilerek ucuzdur (JSON: çalışıyor mu, analiz açık mı, model durumu).
Ana sayfa `veri/` klasörünün tamamını tarayıp boyut hesapladığı için sağlık
kontrolünde kullanılmaz.

---

## 3. Güncelleme

```bash
git pull
docker compose build
docker compose up -d
docker compose logs -f --tail=100
```

Şema değişikliği varsa açılışta kendiliğinden uygulanır. Geri alma:
`git checkout <önceki-sürüm>` → `docker compose build` → `up -d`.

> Şema betikleri **geri alınamaz** (Alembic yoktur — `docs/09` kararı). Geri
> dönüş yolu yedektir: sürüm yükseltmeden ÖNCE `veri/` klasörünü kopyalayın.

---

## 4. Yedekleme

**Tam yedek = `veri/` klasörünü ve `.env` dosyasını kopyalamak.** Hepsi bu.

```bash
cp -R veri/ /yedek/dalsan-$(date +%Y-%m-%d)/
cp .env    /yedek/dalsan-$(date +%Y-%m-%d)/
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
| KKD hiç olay üretmiyor | Model henüz eğitilmedi — bu **beklenen** davranıştır (docs/04). Veri toplanıyor mu: KKD sekmesi |
| KKD çok fazla yanlış alarm | `04-KKD-BARET-YELEK.md` §8.3 tablosu |
| Uyarılar gecikiyor | Kamera `sample_fps` değerini düşürün; substream kullanın; `CIKARIM_CIHAZI=cuda` (yalnız NVIDIA'lı Linux) |
| "cuda seçili ama CPU ile çalışıyor" | Ana sayfada uyarı olarak görünür: NVIDIA sürücüsü + `onnxruntime-gpu` gerekir, ya da `.env`'de `cpu` yapın |
| Anons çalmıyor | **Anons** sayfası → "Anonsu Dene". Sonuç satırı sebebi yazar (ses dosyası yok / adres yanlış / komut bulunamadı) |
| Ekranda uyarı sesi gelmiyor | Tarayıcı kuralı: sayfaya bir kez tıklayın. Anons sayfasındaki kutuyu işaretleyin |
| Disk doluyor | Ana sayfadaki "Boş alan"; saklama sürelerini kısaltın; `veri/goruntuler` en büyük kalemdir |
| Canlı uyarı paneli "bağlantı koptu" | Sunucu durmuş olabilir; Kontrol Paneli'nden yeniden başlatın |

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
- [ ] Bakım (retention) çalıştığı günlükten doğrulandı, KVKK süreleriyle uyumlu
- [ ] **Giriş şifresi geri eklendi** (`docs/07` #0) — ağa açık kurulumda zorunlu
- [ ] Kullanım dokümanı teslim edildi, kullanıcı eğitimi yapıldı (K9)
- [ ] Kabul tutanağı: K1-K11 madde madde işaretlendi
